import os
import uuid
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from auth import roles_required
from models import db, DocFolder, Document, DocumentFile

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
        query_text=query_text
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
