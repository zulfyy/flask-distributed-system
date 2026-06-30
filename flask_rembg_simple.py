from flask import Flask, render_template, request, flash, redirect, session, url_for, send_file
from PIL import Image
import numpy as np
import cv2
from rembg import remove
import io
import base64
import os

app = Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = "bebas_isi_apa_saja_yang_rahasia"

# Folder untuk menyimpan hasil
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def image_to_base64(image_pil):
    """Konversi PIL Image ke base64 string untuk ditampilkan di HTML"""
    buffer = io.BytesIO()
    image_pil.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"

def remove_background(image_pil):
    """
    Menghapus background dari gambar menggunakan rembg
    
    Args:
        image_pil: PIL Image object
        
    Returns:
        PIL Image object dengan background dihapus (RGBA)
    """
    try:
        # Konversi ke RGB jika belum
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')
        
        # Hapus background menggunakan rembg
        image_no_bg = remove(image_pil)
        
        return image_no_bg
    except Exception as e:
        print(f"Error saat menghapus background: {e}")
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
                # Buka gambar original
                image = Image.open(file.stream).convert('RGB')
                
                # HAPUS BACKGROUND menggunakan rembg
                image_no_bg = remove_background(image)
                
                # Simpan ke session untuk ditampilkan
                original_base64 = image_to_base64(image)
                result_base64 = image_to_base64(image_no_bg)
                
                session['original_image'] = original_base64
                session['result_image'] = result_base64
                session['filename'] = file.filename
                
                return redirect(url_for('upload_file'))
                
            except Exception as e:
                flash(f'Error processing image: {str(e)}')
                return redirect(request.url)
        else:
            flash('File type not allowed. Please use: PNG, JPG, JPEG, GIF, WEBP')
            return redirect(request.url)
        
    # Ambil hasil dari session
    original_img = session.get('original_image', None)
    result_img = session.get('result_image', None)
    filename = session.get('filename', None)
    
    return render_template('remove_bg.html', 
                         original_image=original_img, 
                         result_image=result_img,
                         filename=filename)

@app.route('/download')
def download():
    """Download gambar hasil tanpa background"""
    result_img_base64 = session.get('result_image', None)
    original_filename = session.get('filename', 'image')
    
    if result_img_base64:
        # Decode base64 kembali ke image
        img_data = result_img_base64.split(',')[1]
        img_bytes = base64.b64decode(img_data)
        img_buffer = io.BytesIO(img_bytes)
        
        # Ambil nama file tanpa extension
        filename_without_ext = os.path.splitext(original_filename)[0]
        download_filename = f"{filename_without_ext}_no_bg.png"
        
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=download_filename
        )
    else:
        flash('No image to download')
        return redirect(url_for('upload_file'))

@app.route('/clear')
def clear():
    """Hapus session dan kembali ke upload"""
    session.clear()
    return redirect(url_for('upload_file'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
