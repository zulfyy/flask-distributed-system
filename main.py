import os
from flask import Flask, flash, request, redirect, url_for, render_template, send_from_directory
from werkzeug.utils import secure_filename
from database import Database
from config import Config
# from utils import format_tanggal_indo

basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config.from_object(Config)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
# WAJIB: Tambahkan secret key agar fungsi flash() bisa jalan
app.secret_key = app.config['APP_SECRET_KEY'] 
# app.jinja_env.globals['format_tanggal_indo'] = format_tanggal_indo

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

tes = Database(
        serverHost  = app.config['DB_HOST'],
        user        = app.config['DB_USER'],
        password    = app.config['DB_PASSWORD'],
        dbname      = app.config['DB_NAME'],
        port        = app.config['DB_PORT']
    )
tes.connect()
cursor = tes.connection.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id SERIAL PRIMARY KEY,
        nama_file VARCHAR(255) NOT NULL,
        tanggal_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ip_address VARCHAR(45)
    )"""
)


if tes.connect():
    cursor = tes.connection.cursor()
    
    # Cara ngetes koneksi paling valid tanpa perlu bikin table dulu:
    cursor.execute("SELECT version();")
    
    # Ambil hasilnya
    db_version = cursor.fetchone()
    print(f"Koneksi Berhasil! Versi DB lo: {db_version[0]}")
    
    # cursor.close()
    # tes.connection.close()
else:
    print("Wah, koneksi gagal nih.")

# sys.exit(1);

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    user_ip = request.remote_addr

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            sql = "INSERT INTO files (nama_file, ip_address) VALUES (%s, %s)"
            data = (filename, user_ip)
            print("BERHASIL CETAK : %s %s", sql , data);
            cursor.execute(sql, data)
            tes.connection.commit()

            # Sekarang url_for ini akan merujuk ke fungsi download_file di bawah
            flash(f'File "{filename}" berhasil diupload!', 'success')
            return redirect(url_for('upload_file'))
            return redirect(url_for('download_file', name=filename))
            
    # GET — ambil daftar file
    cursor.execute("SELECT id, nama_file, tanggal_upload, ip_address FROM files ORDER BY tanggal_upload DESC")
    data_files = cursor.fetchall()
    # cursor.close()
    return render_template('upload.html', files=data_files, user_ip= user_ip)

# ROUTE BARU: Untuk menampilkan/mendownload file
@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name)

@app.route('/delete/<id>')
def delete_file(id):
    sql = "DELETE FROM files WHERE id =  %s";
    data = (id,)
    cursor.execute(sql,data)
    tes.connection.commit()

    return redirect('/')

if __name__ == '__main__':
    if app.config['APP_MODE'].lower() == 'prod' or app.config['APP_MODE'].lower() == 'production' :
        # Mode Production
        print("Running in PRODUCTION mode")
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        # Mode Development (Default)
        print("Running in DEVELOPMENT mode")
        app.run(host='127.0.0.1', port=5000, debug=True)