from flask import Flask, render_template, request, flash, redirect, url_for
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import os

app = Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'tiff', 'webp'}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = "bebas_isi_apa_saja_yang_rahasia"


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_gps(exif_data):
    """ubah data gps mentah jadi koordinat yang gampang dibaca"""
    gps_info = {}
    if 'GPSInfo' not in exif_data:
        return None

    for key, val in exif_data['GPSInfo'].items():
        tag_name = GPSTAGS.get(key, key)
        gps_info[tag_name] = val

    return gps_info if gps_info else None


def extract_metadata(image_pil, filename):
    info = {}

    info['Filename'] = filename
    info['Format'] = image_pil.format
    info['Mode'] = image_pil.mode
    info['Size'] = f"{image_pil.width} x {image_pil.height} px"

    exif_raw = image_pil.getexif()

    if not exif_raw:
        info['Exif'] = None
        return info

    exif_data = {}
    for tag_id, value in exif_raw.items():
        tag_name = TAGS.get(tag_id, tag_id)
        # ada beberapa value yang formatnya aneh (bytes dll), skip aja biar ga error
        if isinstance(value, bytes):
            try:
                value = value.decode(errors='ignore')
            except Exception:
                continue
        exif_data[tag_name] = value

    gps = extract_gps(exif_data)
    if gps:
        exif_data['GPS'] = gps
        exif_data.pop('GPSInfo', None)

    info['Exif'] = exif_data if exif_data else None
    return info


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    metadata = None

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
                image = Image.open(file.stream)
                metadata = extract_metadata(image, file.filename)
            except Exception as e:
                flash(f'Error reading image: {str(e)}')
                return redirect(request.url)
        else:
            flash('File type not allowed. Please use: PNG, JPG, JPEG, TIFF, WEBP')
            return redirect(request.url)

    return render_template('meta_extract.html', metadata=metadata)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)