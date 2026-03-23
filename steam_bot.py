import requests
from bs4 import BeautifulSoup
import time
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()


TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7" 
}
cookies = {"birthtime": "786240001", "mature_content": "1"}


MIN_INDIRIM = 30  
OYUN_SAYISI = 150 
KABUL_EDILEN_INCELEMELER = ["Son Derece Olumlu", "Çok Olumlu", "Çoğunlukla Olumlu", "Karışık"] 
GONDERILENLER_DOSYASI = "gonderilen_oyunlar.json" 
HEDEF_OYUN_SAYISI = 10
BEKLEME_SURESI_GUN = 14 
MIN_INCELEME_SAYISI = 500 


def gorselli_mesaj_gonder(app_id, mesaj_metni):
    if not TOKEN or not CHAT_ID:
        print("❌ HATA: TOKEN veya CHAT_ID eksik! Lütfen .env dosyasını kontrol et.")
        return False

    gorsel_url = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    veri = {
        "chat_id": CHAT_ID,
        "photo": gorsel_url,
        "caption": mesaj_metni, 
        "parse_mode": "HTML"
    }
    
    yanit = requests.post(url, data=veri)
    
    if yanit.status_code == 200:
        return True
    else:
        print(f"\n❌ GÖRSEL GÖNDERİLEMEDİ! Hata: {yanit.text}\n")
        return False

def fiyat_ve_detay_cek(app_id):
    url = f"https://store.steampowered.com/app/{app_id}/"
    yanit = requests.get(url, headers=headers, cookies=cookies)
    soup = BeautifulSoup(yanit.content, "html.parser")

    indirimli = soup.find("div", class_="discount_final_price")
    normal = soup.find("div", class_="discount_original_price")
    oran = soup.find("div", class_="discount_pct")

    inceleme_durumu = "Bilinmiyor"
    inceleme_sayisi = 0
    review_spans = soup.find_all("span", class_="game_review_summary")
    
    for span in review_spans:
        durum = span.text.strip()
        if durum in KABUL_EDILEN_INCELEMELER:
            inceleme_durumu = durum
            break 
            
    if inceleme_durumu == "Bilinmiyor" and review_spans:
        inceleme_durumu = review_spans[0].text.strip()

    review_meta = soup.find("meta", itemprop="reviewCount")
    if review_meta and review_meta.get("content"):
        try:
            inceleme_sayisi = int(review_meta["content"])
        except ValueError:
            pass

    if indirimli and normal and oran:
        return {
            "normal": normal.text.strip(),
            "indirimli": indirimli.text.strip(),
            "oran": oran.text.strip(),
            "inceleme_durumu": inceleme_durumu,
            "inceleme_sayisi": inceleme_sayisi
        }
    return None

def rakam_ayikla(fiyat_metni):
    temiz = re.sub(r'[^\d.]', '', fiyat_metni)
    return float(temiz) if temiz else 0.0

# --- DAHA ÖNCE GÖNDERİLENLERİ OKU ---
gonderilenler = {}
if os.path.exists(GONDERILENLER_DOSYASI):
    with open(GONDERILENLER_DOSYASI, "r", encoding="utf-8") as f:
        try:
            gonderilenler = json.load(f)
        except json.JSONDecodeError:
            gonderilenler = {} 


try:
    kur_yanit = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
    dolar_kur = kur_yanit.json()["rates"]["TRY"]
    print(f"Güncel Dolar Kuru: {dolar_kur}₺\n")
except:
    dolar_kur = 32.0 
    print("Kur API'si yanıt vermedi, varsayılan kur kullanılıyor.\n")


liste_url = f"https://store.steampowered.com/search/results/?specials=1&json=1&cc=us&count={OYUN_SAYISI}"
yanit = requests.get(liste_url, headers=headers)
oyunlar = yanit.json()["items"]

gonderilecek_oyunlar = [] 
bugun_tarihi = datetime.now()
bugun_tarihi_str = bugun_tarihi.strftime("%Y-%m-%d")

print(f"Tarama Başladı... (En iyi {HEDEF_OYUN_SAYISI} indirim aranıyor)\n")

for oyun in oyunlar:
    if len(gonderilecek_oyunlar) >= HEDEF_OYUN_SAYISI:
        break 

    isim = oyun["name"]
    logo_url = oyun["logo"]
    app_id = logo_url.split("/apps/")[1].split("/")[0]

    if app_id in gonderilenler:
        son_gonderim = datetime.strptime(gonderilenler[app_id], "%Y-%m-%d")
        fark = (bugun_tarihi - son_gonderim).days
        
        if fark < BEKLEME_SURESI_GUN:
            print(f"⏭ {isim} - Yakın zamanda ({fark} gün) gönderildi, atlanıyor.")
            continue

    veri = fiyat_ve_detay_cek(app_id)

    if veri:
        oran_sayi = int(veri["oran"].replace("-", "").replace("%", ""))

        yeterli_indirim_mi = oran_sayi >= MIN_INDIRIM
        iyi_yorumlu_mu = veri["inceleme_durumu"] in KABUL_EDILEN_INCELEMELER
        populer_mi = veri["inceleme_sayisi"] >= MIN_INCELEME_SAYISI 

        if yeterli_indirim_mi and iyi_yorumlu_mu and populer_mi:
            try:
                indirimli_dolar = rakam_ayikla(veri["indirimli"])
                normal_dolar = rakam_ayikla(veri["normal"])
                
                indirimli_tl = round(indirimli_dolar * dolar_kur, 2)
                normal_tl = round(normal_dolar * dolar_kur, 2)
                
                tl_bilgi = f"\n💰 {normal_tl}₺ → <b>{indirimli_tl}₺</b>"
            except Exception:
                tl_bilgi = ""

            print(f"✅ {isim} listeye eklendi!")

            mesaj_metni = (
                f"🎮 <b>{isim}</b>\n"
                f"📉 <b>İndirim:</b> {veri['oran']}\n"
                f"💵 ${normal_dolar} → <b>${indirimli_dolar}</b>"
                f"{tl_bilgi}\n"
                f"⭐ <b>İnceleme:</b> {veri['inceleme_durumu']} <i>({veri['inceleme_sayisi']:,} Oy)</i>\n"
                f"🔗 <a href='https://store.steampowered.com/app/{app_id}/'>Steam'de Görüntüle</a>"
            )
            
            gonderilecek_oyunlar.append({
                "app_id": app_id,
                "isim": isim,
                "mesaj_metni": mesaj_metni
            })
            
        else:
            print(f"❌ {isim} - Şartı sağlamadı (İndirim: %{oran_sayi}, İnceleme: {veri['inceleme_durumu']}, Oy: {veri['inceleme_sayisi']})")

    time.sleep(1) 


if gonderilecek_oyunlar:
    print(f"\n{len(gonderilecek_oyunlar)} Oyun Telegram'a görselleriyle gönderiliyor...\n")
    
    baslik_mesaji = f"🔥 <b>GÜNÜN EN İYİ {len(gonderilecek_oyunlar)} STEAM İNDİRİMİ</b> (1$ = {dolar_kur}₺) 👇"
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": baslik_mesaji, "parse_mode": "HTML"})
    time.sleep(1)

    for oyun in gonderilecek_oyunlar:
        basari = gorselli_mesaj_gonder(oyun["app_id"], oyun["mesaj_metni"])
        if basari:
            print(f"📸 {oyun['isim']} başarıyla gönderildi.")
            gonderilenler[oyun["app_id"]] = bugun_tarihi_str
        
        time.sleep(2) 
    
    with open(GONDERILENLER_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(gonderilenler, f, indent=4)
    print("\n✅ Tüm gönderimler tamamlandı ve hafızaya kaydedildi.")
else:
    print("\nKriterlere uyan yeni oyun bulunamadı.")
