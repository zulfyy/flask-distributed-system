from datetime import datetime

def format_tanggal_indo(date_string):
    # Ubah string ke objek datetime
    if isinstance(date_string, str):
        dt = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S.%f")
    else:
        dt = date_string  # Sudah datetime, langsung pakai
    
    # Daftar nama hari dan bulan
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", 
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    
    # Logika menentukan Pagi, Siang, Sore, atau Malam
    jam = dt.hour
    if 4 <= jam < 11:
        periode = "Pagi"
    elif 11 <= jam < 15:
        periode = "Siang"
    elif 15 <= jam < 19:
        periode = "Sore"
    else:
        periode = "Malam"
        
    # Konversi jam ke format 12 jam
    jam_12 = jam % 12
    if jam_12 == 0: jam_12 = 12
    
    # Gabungkan semua komponen
    hasil = f"{hari[dt.weekday()]}, {dt.day} - {bulan[dt.month-1]} - {dt.year} Jam {jam_12:01d} {periode}"
    return hasil
