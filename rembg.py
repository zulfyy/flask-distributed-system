from flask import Flask, render_template, request, flash, redirect, session, url_for, send_file
from PIL import Image
from rembg import remove, new_session
import io
import os
import uuid

app = Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = "bebas_isi_apa_saja_yang_rahasia"

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# load model sekali aja waktu server nyala, jangan tiap request
# soalnya load model ini berat, bisa bikin lemot kalo dipanggil terus
rembg_session = new_session('isnet-general-use')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def remove_background(image_pil):
    try:
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')

        hasil = remove(
            image_pil,
            session=rembg_session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=5
        )
        return hasil
    except Exception as e:
        print(f"gagal hapus background: {e}")
        return image_pil


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                image = Image.open(file.stream).convert('RGB')
                image_no_bg = remove_background(image)

                file_id = uuid.uuid4().hex

                original_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_original.png")
                result_path = os.path.join(RESULT_FOLDER, f"{file_id}_result.png")

                image.save(original_path, format='PNG')
                image_no_bg.save(result_path, format='PNG')

                # simpan id cookie only, biar cookie ga kegedean
                session['file_id'] = file_id
                session['filename'] = file.filename

                return redirect(url_for('upload_file'))

            except Exception as e:
                flash(f'Error processing image: {str(e)}')
                return redirect(request.url)
        else:
            flash('File type not allowed. Please use: PNG, JPG, JPEG, GIF, WEBP')
            return redirect(request.url)

    file_id = session.get('file_id', None)
    filename = session.get('filename', None)

    original_img = None
    result_img = None
    if file_id:
        original_img = url_for('serve_image', kind='original', file_id=file_id)
        result_img = url_for('serve_image', kind='result', file_id=file_id)

    return render_template('remove_bg.html',
                            original_image=original_img,
                            result_image=result_img,
                            filename=filename)


@app.route('/image/<kind>/<file_id>')
def serve_image(kind, file_id):
    folder = UPLOAD_FOLDER if kind == 'original' else RESULT_FOLDER
    suffix = '_original.png' if kind == 'original' else '_result.png'
    path = os.path.join(folder, f"{file_id}{suffix}")
    if not os.path.exists(path):
        flash('Image not found')
        return redirect(url_for('upload_file'))
    return send_file(path, mimetype='image/png')


@app.route('/download')
def download():
    file_id = session.get('file_id', None)
    original_filename = session.get('filename', 'image')

    if file_id:
        result_path = os.path.join(RESULT_FOLDER, f"{file_id}_result.png")
        if not os.path.exists(result_path):
            flash('No image to download')
            return redirect(url_for('upload_file'))

        filename_without_ext = os.path.splitext(original_filename)[0]
        download_filename = f"{filename_without_ext}_no_bg.png"

        return send_file(
            result_path,
            mimetype='image/png',
            as_attachment=True,
            download_name=download_filename
        )
    else:
        flash('No image to download')
        return redirect(url_for('upload_file'))


@app.route('/clear')
def clear():
    file_id = session.get('file_id')
    if file_id:
        for folder, suffix in [(UPLOAD_FOLDER, '_original.png'), (RESULT_FOLDER, '_result.png')]:
            path = os.path.join(folder, f"{file_id}{suffix}")
            if os.path.exists(path):
                os.remove(path)
    session.clear()
    return redirect(url_for('upload_file'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)