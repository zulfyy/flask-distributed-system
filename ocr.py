from flask import Flask, render_template, request, flash, redirect, session, url_for
import easyocr
from PIL import Image
import numpy as np
import cv2

app = Flask(__name__)
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = "bebas_isi_apa_saja_yang_rahasia"

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

reader = easyocr.Reader(['en','id'], gpu=True)

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
            image = Image.open(file.stream).convert('RGB')
            image_np = np.array(image)

            # Deteksi apakah gambar sudah bersih (std deviasi tinggi = kontras bagus)
            gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            std_dev = gray.std()

            if std_dev > 50:
                # Gambar sudah bersih → JANGAN banyak preprocessing
                processed_img = gray
            else:
                # Gambar buram/rendah kontras → baru pakai preprocessing
                resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                
                _, processed_img = cv2.threshold(
                    resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                # HAPUS erode untuk teks — gunakan dilate jika perlu (menebalkan, bukan mengikis)
                # kernel = np.ones((2,2), np.uint8)
                # processed_img = cv2.dilate(processed_img, kernel, iterations=1)

            result = reader.readtext(
                processed_img,
                paragraph=True,
                text_threshold=0.5,   # turunkan sedikit agar tidak miss karakter
                decoder='greedy',     # lebih cepat & lebih baik untuk teks bersih
            )

            text = " ".join([r[1] for r in result])
            # print(text)

            # SIMPAN HASIL KE SESSION
            session['ocr_result'] = text


            return redirect(url_for('upload_file'))
        
    # Ambil hasil dari session jika ada, lalu hapus agar tidak muncul terus
    result_text = session.pop('ocr_result', None)
    return render_template('ocr.html', result=result_text)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

