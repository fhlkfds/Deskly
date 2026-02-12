import io
import json
import os
import uuid
import zipfile
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from auth import roles_required
from models import db, DocFolder, Document, DocumentFile, AppSetting
from config import Config
from audit_snapshot import _get_drive_service, _upload_to_drive

docs_bp = Blueprint('docs', __name__, url_prefix='/docs')

UPLOAD_ROOT = os.path.join('static', 'uploads', 'docs')


def _ensure_upload_dir():
    os.makedirs(UPLOAD_ROOT, exist_ok=True)


def _save_uploaded_file(upload):
    _ensure_upload_dir()
    original_name = upload.filename or 'upload.bin'
    safe_name = secure_filename(original_name) or 'upload.bin'
    stored_name = f'{uuid.uuid4().hex}_{safe_name}'
    output_path = os.path.join(UPLOAD_ROOT, stored_name)
    upload.save(output_path)
    size_bytes = os.path.getsize(output_path)
    return stored_name, output_path, size_bytes


def _get_setting(key, default=''):
    setting = AppSetting.query.get(key)
    if not setting:
        return default
    return setting.value if setting.value is not None else default


def _setting_enabled(key):
    return _get_setting(key, 'false') == 'true'


def _format_datetime(value):
    if not value:
        return ''
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _doc_filename(doc):
    safe_title = secure_filename(doc.title) or f'document_{doc.id}'
    return f'{doc.id}_{safe_title}.md'


def _build_docs_backup_bundle():
    folders = DocFolder.query.order_by(DocFolder.name).all()
    documents = Document.query.order_by(Document.updated_at.desc()).all()
    files = DocumentFile.query.order_by(DocumentFile.created_at.desc()).all()
    missing_files = []

    payload = {
        'generated_at_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'folders': [
            {
                'id': folder.id,
                'name': folder.name,
                'created_at': _format_datetime(folder.created_at),
            }
            for folder in folders
        ],
        'documents': [
            {
                'id': doc.id,
                'folder_id': doc.folder_id,
                'title': doc.title,
                'content_md': doc.content_md,
                'created_by': doc.created_by,
                'updated_by': doc.updated_by,
                'created_at': _format_datetime(doc.created_at),
                'updated_at': _format_datetime(doc.updated_at),
            }
            for doc in documents
        ],
        'files': [
            {
                'id': file.id,
                'document_id': file.document_id,
                'original_name': file.original_name,
                'stored_name': file.stored_name,
                'relative_path': file.relative_path,
                'mime_type': file.mime_type,
                'size_bytes': file.size_bytes,
                'uploaded_by': file.uploaded_by,
                'created_at': _format_datetime(file.created_at),
            }
            for file in files
        ],
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('docs.json', json.dumps(payload, indent=2, sort_keys=True))
        zf.writestr(
            'README.txt',
            (
                "Documentation Backup\n"
                f"Generated UTC: {payload['generated_at_utc']}\n"
                f"Folders: {len(folders)}\n"
                f"Documents: {len(documents)}\n"
                f"Files: {len(files)}\n"
            ).encode('utf-8')
        )

        for doc in documents:
            folder_name = doc.folder.name if doc.folder else ''
            header = [
                f"# {doc.title}",
                f"Folder: {folder_name}",
                f"Updated: {_format_datetime(doc.updated_at)}",
                "",
            ]
            zf.writestr(
                f"documents/{_doc_filename(doc)}",
                "\n".join(header) + (doc.content_md or '')
            )

        for file in files:
            relative_path = file.relative_path.lstrip('/')
            absolute_path = os.path.join(current_app.root_path, 'static', relative_path)
            if os.path.exists(absolute_path):
                zf.write(absolute_path, arcname=f'attachments/{file.stored_name}')
            else:
                missing_files.append(file.relative_path)

        if missing_files:
            zf.writestr('missing_files.txt', "\n".join(missing_files))

    zip_buffer.seek(0)
    return zip_buffer.read(), missing_files


@docs_bp.route('/')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def index():
    folder_id = request.args.get('folder_id', type=int)
    query_text = request.args.get('q', '').strip()
    folders = DocFolder.query.order_by(DocFolder.name).all()

    query = Document.query
    if folder_id:
        query = query.filter_by(folder_id=folder_id)
    if query_text:
        search_filter = f'%{query_text}%'
        query = query.filter(
            db.or_(
                Document.title.ilike(search_filter),
                Document.content_md.ilike(search_filter)
            )
        )
    documents = query.order_by(Document.updated_at.desc()).all()

    return render_template(
        'docs/index.html',
        folders=folders,
        documents=documents,
        current_folder_id=folder_id,
        query_text=query_text,
        docs_drive_enabled=_setting_enabled('docs_drive_enabled'),
        docs_drive_credentials_file=(Config.DOCS_DRIVE_CREDENTIALS_FILE or '').strip()
    )


@docs_bp.route('/folders/create', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def create_folder():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Folder name is required.', 'warning')
        return redirect(url_for('docs.index'))

    if DocFolder.query.filter(db.func.lower(DocFolder.name) == name.lower()).first():
        flash('Folder already exists.', 'warning')
        return redirect(url_for('docs.index'))

    folder = DocFolder(name=name)
    db.session.add(folder)
    db.session.commit()
    flash('Folder created.', 'success')
    return redirect(url_for('docs.index', folder_id=folder.id))


@docs_bp.route('/new', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def create_document():
    folders = DocFolder.query.order_by(DocFolder.name).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content_md = request.form.get('content_md', '')
        folder_id = request.form.get('folder_id', type=int)
        if not title:
            flash('Title is required.', 'warning')
            return render_template('docs/editor.html', doc=None, folders=folders)

        doc = Document(
            folder_id=folder_id or None,
            title=title,
            content_md=content_md,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(doc)
        db.session.commit()
        flash('Document created.', 'success')
        return redirect(url_for('docs.index'))

    return render_template('docs/editor.html', doc=None, folders=folders)


@docs_bp.route('/<int:doc_id>')
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def view_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return render_template('docs/view.html', doc=doc)


@docs_bp.route('/<int:doc_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def edit_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    folders = DocFolder.query.order_by(DocFolder.name).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content_md = request.form.get('content_md', '')
        folder_id = request.form.get('folder_id', type=int)

        if not title:
            flash('Title is required.', 'warning')
            return render_template('docs/editor.html', doc=doc, folders=folders)

        doc.title = title
        doc.content_md = content_md
        doc.folder_id = folder_id or None
        doc.updated_by = current_user.id
        doc.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Document updated.', 'success')
        return redirect(url_for('docs.index'))

    return render_template('docs/editor.html', doc=doc, folders=folders)


@docs_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk')
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    db.session.delete(doc)
    db.session.commit()
    flash('Document deleted.', 'success')
    return redirect(url_for('docs.index'))


@docs_bp.route('/upload-image', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def upload_image():
    upload = request.files.get('image')
    if not upload:
        return jsonify({'error': 'No image uploaded'}), 400

    if not (upload.mimetype or '').startswith('image/'):
        return jsonify({'error': 'Uploaded file is not an image'}), 400

    stored_name, _, size_bytes = _save_uploaded_file(upload)
    relative_path = f'uploads/docs/{stored_name}'
    file_row = DocumentFile(
        document_id=request.form.get('document_id', type=int),
        original_name=upload.filename or 'image',
        stored_name=stored_name,
        relative_path=relative_path,
        mime_type=upload.mimetype,
        size_bytes=size_bytes,
        uploaded_by=current_user.id
    )
    db.session.add(file_row)
    db.session.commit()

    url = url_for('static', filename=relative_path)
    return jsonify({
        'url': url,
        'markdown': f'![{upload.filename or "image"}]({url})'
    })


@docs_bp.route('/upload-file', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk', 'staff')
def upload_file():
    upload = request.files.get('file')
    if not upload:
        return jsonify({'error': 'No file uploaded'}), 400

    stored_name, _, size_bytes = _save_uploaded_file(upload)
    relative_path = f'uploads/docs/{stored_name}'
    file_row = DocumentFile(
        document_id=request.form.get('document_id', type=int),
        original_name=upload.filename or 'file',
        stored_name=stored_name,
        relative_path=relative_path,
        mime_type=upload.mimetype,
        size_bytes=size_bytes,
        uploaded_by=current_user.id
    )
    db.session.add(file_row)
    db.session.commit()

    url = url_for('static', filename=relative_path)
    return jsonify({
        'url': url,
        'markdown': f'[{upload.filename or "file"}]({url})'
    })


@docs_bp.route('/backup-drive', methods=['POST'])
@login_required
@roles_required('admin', 'helpdesk')
def backup_drive():
    if not _setting_enabled('docs_drive_enabled'):
        flash('Enable documentation backups in Credential Management first.', 'warning')
        return redirect(url_for('docs.index'))

    credentials_file = (Config.DOCS_DRIVE_CREDENTIALS_FILE or '').strip()
    folder_id = (Config.DOCS_DRIVE_FOLDER_ID or '').strip() or None

    if not credentials_file:
        flash('Drive credentials file is required for documentation backups.', 'warning')
        return redirect(url_for('docs.index'))

    try:
        service = _get_drive_service(credentials_file)
        zip_bytes, missing_files = _build_docs_backup_bundle()
        filename = f'docs_backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.zip'
        _upload_to_drive(service, filename, 'application/zip', zip_bytes, folder_id)
        if missing_files:
            flash(f'Backup uploaded. {len(missing_files)} attachment(s) were missing.', 'warning')
        else:
            flash('Backup uploaded to Google Drive.', 'success')
    except Exception as exc:
        flash(f'Failed to upload backup: {str(exc)}', 'danger')

    return redirect(url_for('docs.index'))
