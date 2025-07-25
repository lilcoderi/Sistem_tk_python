from flask import Flask, jsonify
from sqlalchemy import create_engine
import pandas as pd
import numpy as np
import json
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import PolynomialFeatures
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import os
from datetime import datetime
import openai

app = Flask(__name__)
openai.api_key = "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"  # Ganti dengan API Key-mu

nilai_mapping = {'BB': 1, 'MB': 2, 'BSH': 3, 'BSB': 4}

def get_connection():
    engine = create_engine(
        "mysql+pymysql://sistemtkdb_usefulheor:382f83f60b7560c62cad795c7e8b88ca8f9e8626@afl2ht.h.filess.io:61002/sistemtkdb_usefulheor"
    )
    return engine

def konversi_json_ke_skor(nilai_json):
    try:
        if not nilai_json or nilai_json.strip() == "":
            return np.nan
        hasil_parsed = json.loads(nilai_json)
        skor = [nilai_mapping.get(v, np.nan) for v in hasil_parsed.values()]
        return np.nanmean(skor)
    except Exception as e:
        print("Gagal parse nilai_json:", nilai_json)
        print("Error:", str(e))
        return np.nan

def evaluasi_physical(usia_bulan, berat_badan, tinggi_badan, lingkar_kepala):
    # Asumsikan evaluasi tanpa kelamin (hilangkan parameter kelamin)
    tahun = usia_bulan // 12
    # Standar WHO (rata-rata umum tanpa kelamin)
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

@app.route('/ddtk')
def index():
    return '✅ Flask aktif untuk prediksi kesimpulan tumbuh kembang anak!'

@app.route('/predict/<int:id_siswa>', methods=['GET'])
def predict(id_siswa):
    engine = get_connection()
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

    # Konversi JSON ke skor
    df['hasil_skor'] = df['hasil'].apply(konversi_json_ke_skor)

    # Evaluasi fisik (tanpa kelamin)
    df[['bb_normal', 'tb_normal', 'lk_normal']] = df.apply(
        lambda x: pd.Series(evaluasi_physical(x['umur'], x['berat_badan'], x['tinggi_badan'], x['lingkar_kepala'])), axis=1
    )
    df['kesimpulan'] = df.apply(
        lambda x: simpulkan_perkembangan(x['hasil_skor'], x['bb_normal'], x['tb_normal'], x['lk_normal']), axis=1
    )

    # Data training & prediksi
    df_train = df.iloc[:-1].copy()
    df_pred = df.iloc[-1:].copy()

    drop_cols = ['id_siswa', 'nama', 'hasil', 'kesimpulan', 'bb_normal', 'tb_normal', 'lk_normal', 'created_at', 'tanggal_input']
    X_train = df_train.drop(columns=drop_cols, errors='ignore').fillna(0)
    X_pred = df_pred.drop(columns=drop_cols, errors='ignore').fillna(0)

    y_train = df_train['kesimpulan'].map({'Normal': 0, 'Perlu Pengawasan': 1, 'Perlu Rujukan Dokter': 2})

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    prediction = model.predict(X_pred)[0]
    kategori = ['Normal', 'Perlu Pengawasan', 'Perlu Rujukan Dokter'][prediction]

    prompt = f"Buatkan rekomendasi untuk anak usia {int(df_pred['umur'].values[0])} bulan dengan hasil prediksi: {kategori}."
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        rekomendasi = response.choices[0].message.content

    except Exception as e:
        rekomendasi = f"Gagal mendapatkan rekomendasi: {str(e)}"
        
    
    # Keterangan prediktif (arah perkembangan ke depan)
    prompt_keterangan = f"Berdasarkan hasil prediksi tumbuh kembang anak usia {int(df_pred['umur'].values[0])} bulan yang tergolong '{kategori}', bagaimana potensi tumbuh kembang anak ini dalam 6 bulan ke depan? Berikan penjelasan singkat."
    try:
        response_keterangan = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt_keterangan}]
        )
        keterangan = response_keterangan.choices[0].message.content
    except Exception as e:
        keterangan = "Prediksi arah tumbuh kembang tidak tersedia saat ini."

    # Simpan ke database ddtk
    from sqlalchemy import text
    with engine.connect() as conn:
        sql_upsert = text('''
            INSERT INTO ddtk (
                id_siswa,
                id_tumbuhkembang,
                id_hasilasesmenceklis,
                hasil_ddtk,
                rekomendasi,
                keterangan,
                created_at,
                updated_at
            ) VALUES (
                :id_siswa,
                :id_tumbuhkembang,
                :id_hasilasesmenceklis,
                :hasil_ddtk,
                :rekomendasi,
                :keterangan,
                NOW(),
                NOW()
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

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(host='0.0.0.0', port=5000, debug=True)
