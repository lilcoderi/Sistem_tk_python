from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime

app = Flask(__name__)

# --- Koneksi ke DB ---
def get_connection():
    return mysql.connector.connect(
        host='afl2ht.h.filess.io',
        port=61002,
        user='sistemtkdb_usefulheor',
        password='382f83f60b7560c62cad795c7e8b88ca8f9e8626',
        database='sistemtkdb_usefulheor'
    )

# --- Sistem Pakar ---
def sistem_pakar(row):
    rules = []
    score = 0

    # Sosial & Emosional
    if row['pergaulan_dengan_teman'] == 'Kurang':
        score -= 1
        rules.append("Pergaulan kurang, perlu dilatih interaksi sosial.")
    if row['hubungan_dengan_ayah'] in ['Cukup', 'Kurang'] or row['hubungan_dengan_ibu'] in ['Cukup', 'Kurang']:
        score -= 1
        rules.append("Hubungan emosional dengan orang tua perlu ditingkatkan.")
    if row['sikap_anak_dirumah'] == 'Susah diatur':
        score -= 1
        rules.append("Anak perlu pembinaan disiplin atau pendekatan emosional.")

    # Fisik & Kebiasaan
    if row['nafszu_makan'] in ['Kurang', 'Cukup']:
        score -= 1
        rules.append("Nafsu makan kurang maksimal, perhatikan asupan gizi.")
    if row['pagi_hari'] == 'Kurang':
        score -= 1
        rules.append("Aktivitas pagi kurang semangat, perhatikan pola tidur.")
    if row['kebersihan_buang_air'] == 'Dibantu':
        score -= 1
        rules.append("Perlu dilatih buang air secara mandiri.")
    if row['cara_anak_minum_susu'] == 'Masih pakai botol':
        score -= 1
        rules.append("Sebaiknya dilatih minum dengan gelas.")
    if row['apakah_masih_pakai_diaper'] == 'Ya':
        score -= 1
        rules.append("Anak masih pakai diaper, perlu pelatihan toilet.")

    if 'keadaan_waktu_kandungan' in row and row['keadaan_waktu_kandungan'] == 'Tidak':
        score -= 1
        rules.append("Riwayat kehamilan tidak normal, perhatikan tumbuh kembang.")

    # Hasil
    if score <= -5:
        prediksi = "Perlu Perhatian Khusus"
        rekomendasi = "Lakukan pemantauan intensif tumbuh kembang anak dan lakukan observasi lanjutan."
    elif score <= -2:
        prediksi = "Perlu Perhatian"
        rekomendasi = "Perlu bimbingan tambahan di rumah dan sekolah."
    else:
        prediksi = "Kondisi Baik"
        rekomendasi = "Lanjutkan stimulasi dan pemantauan rutin."

    return prediksi, rekomendasi, rules

# --- Endpoint POST untuk prediksi ---
@app.route('/prediksi', methods=['POST'])
def prediksi():
    try:
        id_siswa = request.json['id_siswa']

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
        SELECT a.id AS id_siswa, a.nama_lengkap,
               b.pergaulan_dengan_teman, b.hubungan_dengan_ayah, b.hubungan_dengan_ibu, 
               b.nafszu_makan, b.pagi_hari, b.kebersihan_buang_air, b.sikap_anak_dirumah,
               c.cara_anak_minum_susu, c.apakah_masih_pakai_diaper, c.keadaan_waktu_kandungan
        FROM identitas_anak a
        JOIN kondisi_anak b ON a.id = b.id_siswa
        JOIN keadaan_jasmani c ON a.id = c.id_siswa
        WHERE a.id = %s
        """
        cursor.execute(query, (id_siswa,))
        row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Data siswa tidak ditemukan'}), 404

        prediksi, rekomendasi, catatan = sistem_pakar(row)

        insert_query = """
        INSERT INTO hasil_prediksi_awal 
            (id_siswa, prediksi_awal, rekomendasi_awal, catatan_sistem_pakar, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            id_siswa,
            prediksi,
            rekomendasi,
            "\n- " + "\n- ".join(catatan),
            datetime.now(),
            datetime.now()
        ))
        conn.commit()

        return jsonify({
            'id_siswa': id_siswa,
            'nama_siswa': row['nama_lengkap'],
            'prediksi_awal': prediksi,
            'rekomendasi_awal': rekomendasi,
            'catatan_sistem_pakar': catatan
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Endpoint Cek Server ---
@app.route('/')
def index():
    return '✅ Flask aktif! Gunakan POST ke /prediksi dengan id_siswa'

# --- Jalankan ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
