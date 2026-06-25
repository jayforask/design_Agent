"""
Tasarım Ajanı - Tablo Analizi Modülü
Excel/CSV dosyalarını parse eder, SQLite'a kaydeder,
Gemini ile doğal dil sorguları yanıtlar ve grafik üretir.
"""

import os
import io
import sqlite3
import logging
import json
import urllib.request
import urllib.error
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # GUI gerektirmeyen backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

logger = logging.getLogger(__name__)

# Veritabanı dosya yolu
_DB_DIR = Path(__file__).parent.parent / "memory_store"
_DB_PATH = _DB_DIR / "tables.db"

# Desteklenen dosya uzantıları
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# Grafik anahtar kelimeleri
_CHART_KEYWORDS = [
    "grafik", "chart", "çiz", "görselleştir", "bar", "pie", "pasta",
    "histogram", "scatter", "line chart", "çizgi grafik", "sütun grafik",
    "dağılım", "trend", "plot",
]

# Tablo sorusu anahtar kelimeleri
_TABLE_KEYWORDS = [
    "tabloda", "veride", "dosyada", "excel", "csv", "satır", "sütun",
    "ortalama", "toplam", "maksimum", "minimum", "en fazla", "en az",
    "kaç tane", "analiz", "istatistik", "özet", "hangi", "listele",
    "sırala", "filtrele", "göster", "bul", "ara",
]


# ---------------------------------------------------------------------------
# Veritabanı başlatma
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Veritabanı tablolarını oluşturur (yoksa)."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                row_count INTEGER,
                columns TEXT,  -- JSON listesi
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON uploaded_tables(user_id)
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Dosya yükleme ve parse
# ---------------------------------------------------------------------------

def parse_and_save(
    user_id: int,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Excel veya CSV dosyasını parse eder ve SQLite'a kaydeder.

    Args:
        user_id: Telegram kullanıcı ID'si
        file_bytes: Dosya içeriği (bytes)
        filename: Orijinal dosya adı

    Returns:
        {
            "table_name": "...",
            "row_count": int,
            "columns": [...],
            "summary": "..."  # Telegram'a gönderilecek özet
        }
    """
    init_db()
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Desteklenmeyen dosya formatı: {ext}. Desteklenenler: {', '.join(SUPPORTED_EXTENSIONS)}")

    # Dosyayı pandas ile oku
    try:
        if ext == ".csv":
            # Encoding tespiti için birkaç farklı encoding dene
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1254"]:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as exc:
        raise RuntimeError(f"Dosya okunamadı: {exc}") from exc

    if df.empty:
        raise ValueError("Dosya boş veya veri içermiyor.")

    # Tablo adı: user_id + temizlenmiş dosya adı
    base_name = Path(filename).stem
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in base_name)
    table_name = f"u{user_id}_{safe_name}".lower()[:50]

    # Sütun adlarını temizle (SQLite uyumlu)
    df.columns = [
        "".join(c if c.isalnum() or c == "_" else "_" for c in str(col)).lower()
        for col in df.columns
    ]
    # Boş sütun adlarını düzelt
    df.columns = [f"col_{i}" if not col else col for i, col in enumerate(df.columns)]

    # SQLite'a kaydet (varsa üzerine yaz)
    with sqlite3.connect(_DB_PATH) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)

        # Metadata kaydet
        conn.execute("""
            INSERT OR REPLACE INTO uploaded_tables
                (user_id, table_name, original_filename, row_count, columns)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            table_name,
            filename,
            len(df),
            json.dumps(list(df.columns)),
        ))
        conn.commit()

    logger.info("Tablo kaydedildi: %s (%d satır, %d sütun)", table_name, len(df), len(df.columns))

    # Özet istatistikler
    summary = _build_summary(df, filename, table_name)
    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),
        "summary": summary,
    }


def _build_summary(df: pd.DataFrame, filename: str, table_name: str) -> str:
    """Veri çerçevesinin kısa özetini döndürür."""
    lines = [
        f"✅ *{filename}* yüklendi!",
        f"📊 {len(df)} satır | {len(df.columns)} sütun",
        "",
        "*Sütunlar:*",
    ]

    for col in df.columns[:15]:  # En fazla 15 sütun göster
        dtype = df[col].dtype
        if pd.api.types.is_numeric_dtype(dtype):
            lines.append(f"  • `{col}` — sayısal (min: {df[col].min():.2g}, max: {df[col].max():.2g})")
        else:
            unique = df[col].nunique()
            lines.append(f"  • `{col}` — metin ({unique} benzersiz değer)")

    if len(df.columns) > 15:
        lines.append(f"  _...ve {len(df.columns) - 15} sütun daha_")

    lines.append("")
    lines.append("💬 Soru sorabilirsin: \"Toplam satış kaç?\", \"Bar grafik çiz\"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tablo listesi ve silme
# ---------------------------------------------------------------------------

def list_user_tables(user_id: int) -> list[dict]:
    """Kullanıcının yüklediği tüm tabloları listeler."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT table_name, original_filename, row_count, columns, created_at
            FROM uploaded_tables
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()

    return [
        {
            "table_name": r[0],
            "original_filename": r[1],
            "row_count": r[2],
            "columns": json.loads(r[3]) if r[3] else [],
            "created_at": r[4],
        }
        for r in rows
    ]


def delete_table(user_id: int, table_name: str) -> bool:
    """Kullanıcının tablosunu siler. Başarılıysa True döner."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        # Tablonun bu kullanıcıya ait olduğunu doğrula
        cursor = conn.execute("""
            SELECT table_name FROM uploaded_tables
            WHERE user_id = ? AND table_name = ?
        """, (user_id, table_name))
        row = cursor.fetchone()

        if not row:
            return False

        # SQLite tablosunu sil
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.execute("""
            DELETE FROM uploaded_tables WHERE user_id = ? AND table_name = ?
        """, (user_id, table_name))
        conn.commit()

    logger.info("Tablo silindi: %s (user: %d)", table_name, user_id)
    return True


def format_table_list(tables: list[dict]) -> str:
    """Tablo listesini Telegram formatında döndürür."""
    if not tables:
        return "📭 Henüz tablo yüklemediniz.\n\nExcel veya CSV dosyası göndererek başlayın."

    lines = ["📋 *Yüklü Tablolarınız:*\n"]
    for i, t in enumerate(tables, 1):
        name = t["original_filename"]
        rows = t["row_count"]
        cols = len(t["columns"])
        date = t["created_at"][:10] if t["created_at"] else "?"
        lines.append(f"{i}. *{name}*")
        lines.append(f"   {rows} satır | {cols} sütun | {date}")
        lines.append(f"   ID: `{t['table_name']}`")
        lines.append("")

    lines.append("💡 Soru sormak için tablodan bahset: \"tablomda en yüksek değer ne?\"")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gemini ile sorgulama
# ---------------------------------------------------------------------------

def get_latest_table(user_id: int) -> Optional[dict]:
    """Kullanıcının en son yüklediği tabloyu döndürür."""
    tables = list_user_tables(user_id)
    return tables[0] if tables else None


def load_table_data(table_name: str, max_rows: int = 200) -> Optional[pd.DataFrame]:
    """SQLite'tan tablo verisini yükler."""
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            df = pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT {max_rows}', conn)
        return df
    except Exception as exc:
        logger.error("Tablo yüklenemedi %s: %s", table_name, exc)
        return None


def query_with_gemini(
    user_id: int,
    question: str,
    gemini_api_key: str,
    gemini_model: str,
) -> dict:
    """
    Kullanıcının sorusunu Gemini ile tablo verisi üzerinde yanıtlar.

    Returns:
        {
            "answer": str,          # Metin yanıt
            "chart_path": str|None, # Grafik dosya yolu (oluşturulduysa)
            "chart_type": str|None, # "bar", "pie", "line" vb.
        }
    """
    table_info = get_latest_table(user_id)
    if not table_info:
        return {
            "answer": "⚠️ Henüz tablo yüklemediniz. Bir Excel veya CSV dosyası gönderin.",
            "chart_path": None,
            "chart_type": None,
        }

    df = load_table_data(table_info["table_name"])
    if df is None or df.empty:
        return {
            "answer": "⚠️ Tablo verisi yüklenemedi.",
            "chart_path": None,
            "chart_type": None,
        }

    # Grafik isteği var mı?
    chart_type = _detect_chart_type(question)

    # Veri özetini hazırla (Gemini token limitine dikkat)
    data_preview = _prepare_data_preview(df)

    # Gemini promptu
    prompt = f"""Aşağıdaki tablo verisi hakkında kullanıcının sorusunu yanıtla.

TABLO BILGISI:
Dosya: {table_info['original_filename']}
Satır sayısı: {table_info['row_count']}
Sütunlar: {', '.join(table_info['columns'])}

VERİ ÖNİZLEMESİ (ilk {min(len(df), 50)} satır):
{data_preview}

KULLANICI SORUSU: {question}

TALIMATLAR:
- Soruyu doğrudan ve net yanıtla
- Sayısal sonuçları formatla (1.000 yerine 1000 gibi)
- Türkçe yanıtla
- Eğer grafik isteniyorsa "{chart_type or 'yok'}" grafik türü için hangi sütunların kullanılacağını belirt: JSON formatında {{"x_column": "sütun_adı", "y_column": "sütun_adı", "title": "başlık"}}
- Sadece metin yanıt gerekiyorsa JSON olmadan yanıtla"""

    try:
        gemini_response = _call_gemini_raw(prompt, gemini_api_key, gemini_model)
    except Exception as exc:
        logger.error("Gemini sorgu hatası: %s", exc)
        return {
            "answer": f"⚠️ Analiz sırasında hata oluştu: {str(exc)[:200]}",
            "chart_path": None,
            "chart_type": None,
        }

    # Grafik oluştur (isteniyorsa)
    chart_path = None
    if chart_type:
        chart_config = _extract_chart_config(gemini_response)
        if chart_config:
            chart_path = _generate_chart(df, chart_type, chart_config, table_info["original_filename"])

    # Yanıttan JSON kısmını temizle
    clean_answer = _clean_gemini_response(gemini_response)

    return {
        "answer": clean_answer,
        "chart_path": chart_path,
        "chart_type": chart_type,
    }


def _prepare_data_preview(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Tablo verisinin metin özetini hazırlar."""
    preview_df = df.head(max_rows)

    # İstatistik özeti
    lines = []
    
    # Sayısal sütunlar için istatistik
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        stats = df[numeric_cols].describe().round(2)
        lines.append("İstatistikler:")
        lines.append(stats.to_string())
        lines.append("")

    # Veri önizlemesi
    lines.append("İlk satırlar:")
    lines.append(preview_df.to_string(index=False, max_cols=20))

    return "\n".join(lines)[:3000]  # Token limitini aşmamak için


def _detect_chart_type(text: str) -> Optional[str]:
    """Kullanıcı metninden grafik türünü tespit eder."""
    lower = text.lower()

    if any(w in lower for w in ["pasta", "pie", "pasta grafik", "pie chart"]):
        return "pie"
    if any(w in lower for w in ["çizgi", "line", "trend", "zaman serisi"]):
        return "line"
    if any(w in lower for w in ["scatter", "dağılım", "nokta"]):
        return "scatter"
    if any(w in lower for w in ["bar", "sütun grafik", "çubuk"]):
        return "bar"
    if any(w in lower for w in ["histogram"]):
        return "histogram"
    if any(w in lower for w in ["grafik", "chart", "çiz", "görselleştir", "plot"]):
        return "bar"  # Varsayılan

    return None


def _extract_chart_config(gemini_text: str) -> Optional[dict]:
    """Gemini yanıtından grafik konfigürasyonunu JSON olarak çıkarır."""
    try:
        # JSON bloğunu bul
        start = gemini_text.find("{")
        end = gemini_text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        json_str = gemini_text[start:end]
        config = json.loads(json_str)
        if "x_column" in config or "y_column" in config:
            return config
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def _generate_chart(
    df: pd.DataFrame,
    chart_type: str,
    config: dict,
    title: str = "",
) -> Optional[str]:
    """
    Matplotlib ile grafik oluşturur ve geçici dosyaya kaydeder.

    Returns:
        Grafik PNG dosya yolu veya None
    """
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        plt.rcParams["font.family"] = "DejaVu Sans"

        x_col = config.get("x_column")
        y_col = config.get("y_column")
        chart_title = config.get("title", title)

        if chart_type == "pie" and y_col and y_col in df.columns:
            label_col = x_col if x_col and x_col in df.columns else df.columns[0]
            data = df.groupby(label_col)[y_col].sum()
            ax.pie(data.values, labels=data.index, autopct="%1.1f%%", startangle=90)
            ax.set_title(chart_title)

        elif chart_type == "bar" and y_col and y_col in df.columns:
            label_col = x_col if x_col and x_col in df.columns else df.columns[0]
            plot_df = df.groupby(label_col)[y_col].sum().reset_index()
            if len(plot_df) > 20:
                plot_df = plot_df.nlargest(20, y_col)
            ax.bar(plot_df[label_col].astype(str), plot_df[y_col])
            ax.set_xlabel(label_col)
            ax.set_ylabel(y_col)
            ax.set_title(chart_title)
            plt.xticks(rotation=45, ha="right")

        elif chart_type == "line" and y_col and y_col in df.columns:
            x_data = df[x_col] if x_col and x_col in df.columns else df.index
            ax.plot(x_data, df[y_col], marker="o", linewidth=2)
            ax.set_xlabel(x_col or "Index")
            ax.set_ylabel(y_col)
            ax.set_title(chart_title)
            plt.xticks(rotation=45, ha="right")

        elif chart_type == "scatter" and x_col and y_col and x_col in df.columns and y_col in df.columns:
            ax.scatter(df[x_col], df[y_col], alpha=0.6)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.set_title(chart_title)

        elif chart_type == "histogram" and y_col and y_col in df.columns:
            ax.hist(df[y_col].dropna(), bins=20, edgecolor="black")
            ax.set_xlabel(y_col)
            ax.set_ylabel("Frekans")
            ax.set_title(chart_title)

        else:
            # Fallback: ilk sayısal sütunun histogramı
            num_cols = df.select_dtypes(include="number").columns
            if len(num_cols) > 0:
                ax.hist(df[num_cols[0]].dropna(), bins=20, edgecolor="black")
                ax.set_title(f"{num_cols[0]} Dağılımı")
            else:
                plt.close(fig)
                return None

        plt.tight_layout()

        # Geçici dosyaya kaydet
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        plt.savefig(tmp.name, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info("Grafik oluşturuldu: %s", tmp.name)
        return tmp.name

    except Exception as exc:
        logger.error("Grafik oluşturma hatası: %s", exc)
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _call_gemini_raw(prompt: str, api_key: str, model: str) -> str:
    """Gemini API'ye ham istek gönderir."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Gemini API hatası {exc.code}: {exc.read().decode()}") from exc


def _clean_gemini_response(text: str) -> str:
    """Gemini yanıtından JSON bloklarını temizler."""
    lines = text.split("\n")
    clean_lines = []
    in_json = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{") and ("x_column" in stripped or "y_column" in stripped):
            in_json = True
        if not in_json:
            clean_lines.append(line)
        if in_json and stripped.endswith("}"):
            in_json = False

    result = "\n".join(clean_lines).strip()
    return result if result else text.strip()


def detect_table_question(text: str) -> bool:
    """Kullanıcı metninin tablo sorusu olup olmadığını tespit eder."""
    lower = text.lower()
    return any(kw in lower for kw in _TABLE_KEYWORDS + _CHART_KEYWORDS)
