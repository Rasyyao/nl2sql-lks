import sqlite3
from typing import Dict, List, Any
from datetime import datetime


SCHEMA_SUMMARY_LKS = """\
=== STRUKTUR DATABASE UNIVERSITAS ===

TABEL: dosen
  Kolom: id_dosen (INT (PK)), nidn (varchar(20)), nama_lengkap (varchar(150)), jenis_kelamin (TEXT), id_fakultas (INT (FK→fakultas.id_fakultas)), id_jabatan (INT (FK→jabatan_fungsional.id_jabatan)), pendidikan_terakhir (TEXT), usia (INT), tanggal_bergabung (date), status_kepegawaian (TEXT), foto (varchar(255))
  Contoh data: id_dosen=1, nidn='210871520', nama_lengkap='Bella Mardian Lestari, S.Kom., M.Kom', jenis_kelamin='P', id_fakultas=4, foto='/foto/juri1.png'
  Nilai jenis_kelamin: 'P', 'L'
  Nilai pendidikan_terakhir: 'S2', 'S3'
  Nilai status_kepegawaian: 'Tetap', 'DPK', 'Kontrak'
  Kolom foto: menyimpan path file gambar, format '/foto/<namafile>.<ext>'. Contoh: '/foto/juri1.png'. Untuk INSERT foto gunakan path yang sudah diupload.

TABEL: fakultas
  Kolom: id_fakultas (INT (PK)), nama_fakultas (varchar(100)), kode_fakultas (varchar(10)), dekan (varchar(100)), id_dekan (INT (FK→dosen.id_dosen))
  Contoh data: id_fakultas=1, nama_fakultas='Fakultas Matematika dan IPA', kode_fakultas='FMIPA', dekan='Prof. Dr. Hendra Kusuma, M.Si', id_dekan=None

TABEL: jabatan_fungsional
  Kolom: id_jabatan (INT (PK)), nama_jabatan (varchar(50)), kode_jabatan (varchar(10)), angka_kredit_min (INT)
  Contoh data: id_jabatan=1, nama_jabatan='Asisten Ahli', kode_jabatan='AA', angka_kredit_min=150

TABEL: remunerasi
  Kolom: id_remunerasi (INT (PK)), id_dosen (INT (FK→dosen.id_dosen)), tahun (INT), bulan (INT), gaji_pokok (decimal(12,2)), tunjangan_jabatan (decimal(12,2)), tunjangan_fungsional (decimal(12,2)), tunjangan_kinerja (decimal(12,2))
  Contoh data: id_remunerasi=1, id_dosen=1, tahun=2025, bulan=1, gaji_pokok=5931672.7

────────────────────────────────────────────────────────────
RELASI ANTAR TABEL (FK):
  dosen.id_jabatan    → jabatan_fungsional.id_jabatan  (isi dengan SELECT id_jabatan FROM jabatan_fungsional WHERE nama_jabatan LIKE '%...%')
  dosen.id_fakultas   → fakultas.id_fakultas           (isi dengan SELECT id_fakultas FROM fakultas WHERE nama_fakultas LIKE '%...%')
  fakultas.id_dekan   → dosen.id_dosen                 (isi dengan SELECT id_dosen FROM dosen WHERE nama_lengkap LIKE '%...%')
  remunerasi.id_dosen → dosen.id_dosen                 (isi dengan SELECT id_dosen FROM dosen WHERE nama_lengkap LIKE '%...%')

ATURAN INSERT FK:
  - Kolom PK (id_dosen, id_fakultas, id_jabatan, id_remunerasi): gunakan (SELECT COALESCE(MAX(id_xxx), 0) + 1 FROM tabel)
  - Kolom FK (id_dekan, id_fakultas di dosen, id_jabatan di dosen, id_dosen di remunerasi):
    JANGAN MAX+1! Gunakan SELECT untuk mencari ID yang sudah ada di tabel relasi berdasarkan nama.
"""

def get_schema_summary(db_path: str = None) -> str:
    return SCHEMA_SUMMARY_LKS
