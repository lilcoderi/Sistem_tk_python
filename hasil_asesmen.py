from flask import Flask, request, jsonify
import pymysql
import json
from datetime import datetime
import openai
import re

app = Flask(__name__)

# API Key OpenAI
openai.api_key = "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"

# Koneksi ke database MySQL
def get_connection():
    return pymysql.connect(
        host='afl2ht.h.filess.io',
        port=61002,
        user='sistemtkdb_usefulheor',
        password='382f83f60b7560c62cad795c7e8b88ca8f9e8626',
        db='sistemtkdb_usefulheor',
        cursorclass=pymysql.cursors.DictCursor
    )

# Konversi label ke angka
def label_ke_nilai(label):
    return {'BB': 1, 'MB': 2, 'BSH': 3, 'BSB': 4}.get(label, 0)

# Fungsi: Generate rekomendasi & catatan dari GPT lalu pisahkan
def generate_rekomendasi_catatan_gpt(hasil_lingkup, nama_siswa):
    prompt = f"""
Buatkan rekomendasi dan catatan perkembangan anak berdasarkan hasil asesmen berikut:

Nama anak: {nama_siswa}
Hasil per lingkup perkembangan:
{json.dumps(hasil_lingkup, ensure_ascii=False, indent=2)}

Gunakan format:
- Rekomendasi: (maksimal 4-5 poin, singkat, praktis, berbasis hasil asesmen)
- Catatan: (observasi umum, motivasi untuk pendidik/orang tua)

Jawaban:
"""
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Kamu adalah seorang psikolog anak dan pendidik anak usia dini."},
                {"role": "user", "content": prompt}
            ]
        )
        full_output = response.choices[0].message.content

        # Pisahkan Rekomendasi dan Catatan
        rekomendasi_match = re.search(r"- Rekomendasi:\s*(.*?)(- Catatan:|$)", full_output, re.DOTALL)
        catatan_match = re.search(r"- Catatan:\s*(.*)", full_output, re.DOTALL)

        rekomendasi = rekomendasi_match.group(1).strip() if rekomendasi_match else "Tidak tersedia."
        catatan = catatan_match.group(1).strip() if catatan_match else "Tidak tersedia."

        return rekomendasi, catatan

    except Exception as e:
        return f"Gagal menghasilkan rekomendasi dari ChatGPT: {e}", "-"

# Fungsi utama sistem pakar
def jalankan_sistem_pakar(id_siswa, id_asesmen):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Ambil nama siswa
        cursor.execute("SELECT nama_lengkap FROM identitas_anak WHERE id = %s", (id_siswa,))
        siswa = cursor.fetchone()
        if not siswa:
            return {'error': f'Siswa dengan ID {id_siswa} tidak ditemukan.'}

        nama_siswa = siswa['nama_lengkap']

        # Ambil semua lingkup perkembangan
        cursor.execute("SELECT id, nama_lingkup FROM lingkup_perkembangan")
        lingkup_list = cursor.fetchall()

        hasil_lingkup = {}
        semua_bagus = True
        tanggal_proses = datetime.now().strftime('%Y-%m-%d')

        for lingkup in lingkup_list:
            id_lingkup = lingkup['id']
            nama_lingkup = lingkup['nama_lingkup']

            # Ambil nilai per lingkup
            cursor.execute("""
                SELECT da.skala_nilai
                FROM detail_asesmen da
                JOIN modul_ajar ma ON da.modulajar_id = ma.id
                WHERE da.id_asesmen = %s AND ma.lingkup_id = %s
            """, (id_asesmen, id_lingkup))
            nilai_list = cursor.fetchall()

            nilai_angka = [label_ke_nilai(n['skala_nilai']) for n in nilai_list if n['skala_nilai']]

            if not nilai_angka:
                hasil_lingkup[nama_lingkup] = 'Tidak ada data'
                semua_bagus = False
                continue

            total_nilai = sum(nilai_angka)
            maks_nilai = len(nilai_angka) * 4
            persentase = (total_nilai / maks_nilai) * 100

            if persentase <= 40:
                label = 'BB'
            elif persentase <= 60:
                label = 'MB'
            elif persentase <= 80:
                label = 'BSH'
            else:
                label = 'BSB'

            hasil_lingkup[nama_lingkup] = label
            semua_bagus = semua_bagus and label == 'BSB'

        # Ambil rekomendasi & catatan dari GPT
        rekomendasi_str, catatan_str = generate_rekomendasi_catatan_gpt(hasil_lingkup, nama_siswa)

        # Simpan hasil ke DB
        cursor.execute("""
            INSERT INTO hasil_asesmen_ceklis (id_siswa, id_asesmen, tanggal_proses, hasil, rekomendasi, catatan)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                tanggal_proses = VALUES(tanggal_proses),
                hasil = VALUES(hasil),
                rekomendasi = VALUES(rekomendasi),
                catatan = VALUES(catatan)
        """, (
            id_siswa,
            id_asesmen,
            tanggal_proses,
            json.dumps(hasil_lingkup, ensure_ascii=False),
            rekomendasi_str,
            catatan_str
        ))
        conn.commit()

        return {
            'id_siswa': id_siswa,
            'id_asesmen': id_asesmen,
            'nama_siswa': nama_siswa,
            'tanggal_proses': tanggal_proses,
            'hasil_per_lingkup': hasil_lingkup,
            'rekomendasi': rekomendasi_str,
            'catatan': catatan_str
        }

    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        cursor.close()
        conn.close()

# Endpoint POST dari Laravel
@app.route('/hasilasesmen', methods=['POST'])
def hasilasesmen():
    try:
        data = request.get_json()
        if not data or 'id_siswa' not in data or 'id_asesmen' not in data:
            return jsonify({'error': 'Parameter id_siswa dan id_asesmen diperlukan'}), 400

        hasil = jalankan_sistem_pakar(data['id_siswa'], data['id_asesmen'])

        if 'error' in hasil:
            return jsonify(hasil), 404

        return jsonify(hasil)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint tes koneksi
@app.route('/asesmen')
def index():
    return '✅ Flask Sistem Pakar aktif! POST ke /hasilasesmen'

# Jalankan server Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
