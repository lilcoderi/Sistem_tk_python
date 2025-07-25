from flask import Flask, request, jsonify
from datetime import datetime
import os

# ========== Bagian Prediksi Awal ==========
import mysql.connector

# ========== Bagian Predict DDTK ==========
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np
import json
from sklearn.ensemble import RandomForestClassifier
import matplotlib
matplotlib.use('Agg')

# ========== Bagian Hasil Asesmen ==========
import pymysql
import re
import openai

# ================== FLASK APP ==================
app = Flask(__name__)

# =====================================================
# ---------- FUNGSI UNTUK PREDIKSI_AWAL -------------
# =====================================================
def get_connection_prediksi_awal():
    return mysql.connector.connect(
        host='afl2ht.h.filess.io',
        port=61002,
        user='sistemtkdb_usefulheor',
        password='382f83f60b7560c62cad795c7e8b88ca8f9e8626',
        database='sistemtkdb_usefulheor'
    )

def sistem_pakar_awal(row):
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

@app.route('/prediksi', methods=['POST'])
def prediksi_awal():
    try:
        id_siswa = request.json['id_siswa']
        conn = get_connection_prediksi_awal()
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

        prediksi, rekomendasi, catatan = sistem_pakar_awal(row)
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

@app.route('/')
def index():
    return '✅ Flask aktif! Gunakan endpoint yang tersedia (/prediksi, /predict/<id>, /hasilasesmen)'

# =====================================================
# ---------- FUNGSI UNTUK PREDICT_DDTK ---------------
# =====================================================
def get_connection_ddtk():
    engine = create_engine(
        "mysql+pymysql://sistemtkdb_usefulheor:382f83f60b7560c62cad795c7e8b88ca8f9e8626@afl2ht.h.filess.io:61002/sistemtkdb_usefulheor"
    )
    return engine

nilai_mapping = {'BB': 1, 'MB': 2, 'BSH': 3, 'BSB': 4}

def konversi_json_ke_skor(nilai_json):
    try:
        if not nilai_json or nilai_json.strip() == "":
            return np.nan
        hasil_parsed = json.loads(nilai_json)
        skor = [nilai_mapping.get(v, np.nan) for v in hasil_parsed.values()]
        return np.nanmean(skor)
    except:
        return np.nan

def evaluasi_physical(usia_bulan, berat_badan, tinggi_badan, lingkar_kepala):
    tahun = usia_bulan // 12
    bb_standar = {4: (14.0, 18.0), 5: (15.0, 20.0), 6: (17.0, 23.0)}
    tb_standar = {4: (95, 105), 5: (101, 115), 6: (107, 121)}
    lk_standar = {4: (47, 50), 5: (47, 51), 6: (48, 51)}
    bb_min, bb_max = bb_standar.get(tahun, (0, 0))
    tb_min, tb_max = tb_standar.get(tahun, (0, 0))
    lk_min, lk_max = lk_standar.get(tahun, (0, 0))
    bb_normal = 'Ya' if (bb_min <= berat_badan <= bb_max) else 'Tidak'
    tb_normal = 'Ya' if (tb_min <= tinggi_badan <= tb_max) else 'Tidak'
    lk_normal = 'Ya' if (lk_min <= lingkar_kepala <= lk_max) else 'Tidak'
    return bb_normal, tb_normal, lk_normal

def simpulkan_perkembangan(hasil_skor, bb_normal, tb_normal, lk_normal):
    indikator_tdk_normal = sum([bb_normal == 'Tidak', tb_normal == 'Tidak', lk_normal == 'Tidak'])
    if hasil_skor >= 3.25 and indikator_tdk_normal == 0:
        return "Normal"
    elif hasil_skor >= 2.0 and indikator_tdk_normal <= 1:
        return "Perlu Pengawasan"
    else:
        return "Perlu Rujukan Dokter"

openai.api_key = "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"  # Ganti dengan API Key-mu

@app.route('/predict/<int:id_siswa>', methods=['GET'])
def predict_ddtk(id_siswa):
    engine = get_connection_ddtk()
    query = f'''
        SELECT ia.id AS id_siswa, ia.nama_lengkap AS nama,
               ac.id AS id_hasilasesmenceklis, ac.hasil,
               tk.id AS id_tumbuhkembang, tk.tinggi_badan, tk.berat_badan,
               tk.lingkar_kepala, tk.umur, tk.tanggal_input, tk.created_at
        FROM identitas_anak ia
        LEFT JOIN hasil_asesmen_ceklis ac ON ia.id = ac.id_siswa
        LEFT JOIN tumbuh_kembang tk ON ia.id = tk.id_siswa
        WHERE ia.id = {id_siswa}
        ORDER BY tk.created_at
    '''
    df = pd.read_sql(query, engine)
    if df.empty or df.shape[0] < 3:
        return jsonify({'status': 'error', 'message': 'Data tidak cukup untuk prediksi.'}), 400

    df['hasil_skor'] = df['hasil'].apply(konversi_json_ke_skor)
    df[['bb_normal','tb_normal','lk_normal']] = df.apply(
        lambda x: pd.Series(evaluasi_physical(x['umur'], x['berat_badan'], x['tinggi_badan'], x['lingkar_kepala'])), axis=1
    )
    df['kesimpulan'] = df.apply(
        lambda x: simpulkan_perkembangan(x['hasil_skor'], x['bb_normal'], x['tb_normal'], x['lk_normal']), axis=1
    )
    df_train = df.iloc[:-1].copy()
    df_pred = df.iloc[-1:].copy()
    drop_cols = ['id_siswa','nama','hasil','kesimpulan','bb_normal','tb_normal','lk_normal','created_at','tanggal_input']
    X_train = df_train.drop(columns=drop_cols, errors='ignore').fillna(0)
    X_pred = df_pred.drop(columns=drop_cols, errors='ignore').fillna(0)
    y_train = df_train['kesimpulan'].map({'Normal':0,'Perlu Pengawasan':1,'Perlu Rujukan Dokter':2})
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    prediction = model.predict(X_pred)[0]
    kategori = ['Normal','Perlu Pengawasan','Perlu Rujukan Dokter'][prediction]

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":f"Buatkan rekomendasi untuk anak usia {int(df_pred['umur'].values[0])} bulan dengan hasil prediksi: {kategori}."}]
        )
        rekomendasi = response.choices[0].message.content
    except Exception as e:
        rekomendasi = f"Gagal mendapatkan rekomendasi: {str(e)}"

    try:
        response_keterangan = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":f"Berdasarkan hasil prediksi tumbuh kembang anak usia {int(df_pred['umur'].values[0])} bulan yang tergolong '{kategori}', bagaimana potensi tumbuh kembang anak ini dalam 6 bulan ke depan? Berikan penjelasan singkat."}]
        )
        keterangan = response_keterangan.choices[0].message.content
    except Exception as e:
        keterangan = "Prediksi arah tumbuh kembang tidak tersedia saat ini."

    with engine.connect() as conn:
        sql_upsert = text('''
            INSERT INTO ddtk (
                id_siswa, id_tumbuhkembang, id_hasilasesmenceklis,
                hasil_ddtk, rekomendasi, keterangan, created_at, updated_at
            ) VALUES (
                :id_siswa, :id_tumbuhkembang, :id_hasilasesmenceklis,
                :hasil_ddtk, :rekomendasi, :keterangan, NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                id_tumbuhkembang = VALUES(id_tumbuhkembang),
                id_hasilasesmenceklis = VALUES(id_hasilasesmenceklis),
                hasil_ddtk = VALUES(hasil_ddtk),
                rekomendasi = VALUES(rekomendasi),
                keterangan = VALUES(keterangan),
                updated_at = NOW()
        ''')
        conn.execute(sql_upsert, {
            'id_siswa': int(df_pred['id_siswa'].values[0]),
            'id_tumbuhkembang': int(df_pred['id_tumbuhkembang'].values[0]),
            'id_hasilasesmenceklis': int(df_pred['id_hasilasesmenceklis'].values[0]),
            'hasil_ddtk': kategori,
            'rekomendasi': rekomendasi,
            'keterangan': keterangan
        })
        conn.commit()

    return jsonify({
        'status': 'success',
        'id_siswa': int(df_pred['id_siswa'].values[0]),
        'hasil_prediksi': kategori,
        'rekomendasi': rekomendasi,
        'keterangan': keterangan
    })

# =====================================================
# ---------- FUNGSI UNTUK HASIL_ASESMEN --------------
# =====================================================
def get_connection_asesmen():
    return pymysql.connect(
        host='afl2ht.h.filess.io',
        port=61002,
        user='sistemtkdb_usefulheor',
        password='382f83f60b7560c62cad795c7e8b88ca8f9e8626',
        db='sistemtkdb_usefulheor',
        cursorclass=pymysql.cursors.DictCursor
    )

def label_ke_nilai(label):
    return {'BB': 1, 'MB': 2, 'BSH': 3, 'BSB': 4}.get(label, 0)

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
        rekomendasi_match = re.search(r"- Rekomendasi:\s*(.*?)(- Catatan:|$)", full_output, re.DOTALL)
        catatan_match = re.search(r"- Catatan:\s*(.*)", full_output, re.DOTALL)
        rekomendasi = rekomendasi_match.group(1).strip() if rekomendasi_match else "Tidak tersedia."
        catatan = catatan_match.group(1).strip() if catatan_match else "Tidak tersedia."
        return rekomendasi, catatan
    except Exception as e:
        return f"Gagal menghasilkan rekomendasi dari ChatGPT: {e}", "-"

def jalankan_sistem_pakar(id_siswa, id_asesmen):
    conn = get_connection_asesmen()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nama_lengkap FROM identitas_anak WHERE id = %s", (id_siswa,))
        siswa = cursor.fetchone()
        if not siswa:
            return {'error': f'Siswa dengan ID {id_siswa} tidak ditemukan.'}
        nama_siswa = siswa['nama_lengkap']
        cursor.execute("SELECT id, nama_lingkup FROM lingkup_perkembangan")
        lingkup_list = cursor.fetchall()
        hasil_lingkup = {}
        tanggal_proses = datetime.now().strftime('%Y-%m-%d')
        for lingkup in lingkup_list:
            id_lingkup = lingkup['id']
            nama_lingkup = lingkup['nama_lingkup']
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
        rekomendasi_str, catatan_str = generate_rekomendasi_catatan_gpt(hasil_lingkup, nama_siswa)
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

@app.route('/asesmen')
def asesmen_index():
    return '✅ Flask Sistem Pakar Asesmen aktif! POST ke /hasilasesmen'

# ================== RUN APP ==================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
