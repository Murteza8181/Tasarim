import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
import os
import sys
import json
from pathlib import Path
import threading
import time
import io

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# EXE için yol düzeltmesi
def get_exe_path():
    """EXE veya script yolunu al"""
    if getattr(sys, 'frozen', False):
        # EXE olarak çalışıyor
        return Path(sys.executable).parent
    else:
        # Script olarak çalışıyor
        return Path(__file__).parent

# Uygulama klasörü
UYGULAMA_KLASORU = get_exe_path()

# JPG İzleyici ve Boyutlandırıcı - Lazy import için parent class
try:
    from watchdog.events import FileSystemEventHandler as _WatchdogBase
except ImportError:
    _WatchdogBase = object

class JPGWatcher(_WatchdogBase):
    """Ana klasöre eklenen JPG dosyalarını izler ve boyutlandırır"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.processing = set()  # İşlenen dosyaları takip et (çift işleme önleme)
        self.lock = threading.Lock()
    
    def on_created(self, event):
        """Yeni dosya oluşturulduğunda tetiklenir"""
        print(f"🔔 Dosya tespit edildi: {event.src_path}")
        
        if event.is_directory:
            print("  → Klasör, atlanıyor")
            return
        
        file_path = Path(event.src_path)
        print(f"  → Dosya uzantısı: {file_path.suffix.lower()}")
        
        if file_path.suffix.lower() in ['.jpg', '.jpeg']:
            print("  → JPG dosyası!")
            # Ana klasörlerde mi kontrol et
            aktif_ana_klasor = None
            if self.app.aktif_kategori == "Desenler" and self.app.desenler_ana_klasor:
                aktif_ana_klasor = Path(self.app.desenler_ana_klasor)
            elif self.app.aktif_kategori == "Varyantlar" and self.app.varyantlar_ana_klasor:
                aktif_ana_klasor = Path(self.app.varyantlar_ana_klasor)
            
            print(f"  → Ana klasör: {aktif_ana_klasor}")
            print(f"  → Dosya konumu: {file_path.parent}")
            
            # Dosya ana klasörde mi? (alt klasörlerde değil)
            if aktif_ana_klasor and file_path.parent == aktif_ana_klasor:
                print("  ✅ Ana klasörde! İşleme alınıyor...")
                # Thread-safe işleme
                with self.lock:
                    if str(file_path) not in self.processing:
                        self.processing.add(str(file_path))
                        # Kısa bir bekleme - dosya tam kopyalanana kadar
                        threading.Timer(1.0, self._resize_image, args=(file_path,)).start()
                    else:
                        print("  ⚠ Zaten işleniyor, atlanıyor")
            else:
                print("  ❌ Ana klasörde değil veya klasör tanımlanmamış, atlanıyor")
    
    def _resize_image(self, file_path):
        """Resmi 1200x900'e boyutlandır"""
        print(f"🖼 Boyutlandırma başlıyor: {file_path.name}")
        try:
            # Dosya var mı kontrol et
            if not file_path.exists():
                print(f"  ❌ Dosya bulunamadı: {file_path}")
                with self.lock:
                    self.processing.discard(str(file_path))
                return
            
            print(f"  ✅ Dosya bulundu, yükleniyor...")
            # Resmi yükle
            img = Image.open(file_path)
            original_width, original_height = img.size
            print(f"  📏 Orijinal boyut: {original_width}x{original_height}")
            
            # Zaten küçükse işlem yapma
            if original_width <= 1200 and original_height <= 900:
                print(f"  ⏭ Zaten küçük, işlem yok")
                with self.lock:
                    self.processing.discard(str(file_path))
                return
            
            # En-boy oranını koru
            ratio = min(1200 / original_width, 900 / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            print(f"  🔄 Yeni boyut: {new_width}x{new_height}")
            
            # Boyutlandır
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Geçici dosyaya kaydet
            temp_path = file_path.with_suffix('.tmp')
            print(f"  💾 Kaydediliyor...")
            img_resized.save(temp_path, 'JPEG', quality=95, optimize=True)
            
            # Orijinali değiştir
            os.replace(temp_path, file_path)
            print(f"  ✅ Başarılı! Orijinal dosya değiştirildi")
            
            # UI'da bildirim göster
            self.app.after(0, lambda: self._show_notification(file_path.name, original_width, original_height, new_width, new_height))
            
        except Exception as e:
            print(f"  ❌ Hata: {file_path.name} boyutlandırılırken hata: {e}")
            import traceback
            traceback.print_exc()
        finally:
            with self.lock:
                self.processing.discard(str(file_path))
    
    def _show_notification(self, filename, old_w, old_h, new_w, new_h):
        """Boyutlandırma bildirimini göster"""
        msg = f"✅ {filename}\n{old_w}x{old_h} → {new_w}x{new_h}"
        messagebox.showinfo("Resim Boyutlandırıldı", msg)

class DesenYonetimSistemi(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Pencere ayarları
        self.title("Desen Önizleme ve Yönetim Sistemi")
        self.geometry("1400x900")
        self.minsize(1000, 700)
        
        # Açılışta tam ekran (maksimize) - pencere oluştuktan sonra
        self.after(10, self._maximize_window)
        
        # Veri yapıları - İKİ AYRI ANA KLASÖR
        self.desenler_ana_klasor = None  # Desenler için ana klasör
        self.varyantlar_ana_klasor = None  # Varyantlar için ana klasör
        self.desenler = {}  # {klasor_adi: [{dosya: path, etiket: [], ...}]}
        self.varyantlar = {}  # {klasor_adi: [{dosya: path, etiket: [], ...}]}
        self.aktif_kategori = "Desenler"  # "Desenler" veya "Varyantlar"
        self.aktif_klasor = None
        self.aktif_desen_index = 0
        self.desenler_etiketler_dosyasi = None
        self.varyantlar_etiketler_dosyasi = None
        self.desenler_ayarlar_dosyasi = None
        self.varyantlar_ayarlar_dosyasi = None
        self.desenler_cache_dosyasi = None
        self.varyantlar_cache_dosyasi = None
        self.tam_ekran_pencere = None
        self.filigran_var = ctk.BooleanVar(value=True)  # Filigran varsayılan açık
        self.arama_sonuclari = []  # Arama sonuçlarını sakla (kategori, klasor_adi, desen_index)
        self.secili_desenler = set()  # Seçili desenler {(kategori, klasor_adi, desen_index)}
        self.logo_yolu = None  # Başlıkta gösterilecek logo yolu
        self._logo_ctk_image = None  # CTkImage cache
        self._logo_pil_image = None  # Orijinal PIL görseli, yeniden boyutlandırma için
        self._logo_resize_job = None  # Debounce için after job id
        self._last_logo_size = None   # Son uygulanan (w,h)
        self.thumbnail_cache = {}  # Thumbnail cache - {dosya_yolu: CTkImage}
        self.max_cache_size = 50  # Cache boyutu azaltıldı - daha hızlı
        self._save_after_id = None  # Kaydetme throttle için
        self._arama_after_id = None  # Arama debounce için
        
        # Zoom için değişkenler
        self.zoom_level = 1.0  # 1.0 = normal boyut
        self.min_zoom = 0.5
        self.max_zoom = 3.0
        self.zoom_step = 0.1
        self.current_image_path = None  # Şu anki gösterilen resmin yolu
        
        # Preloading ve animasyon için
        self._preload_cache = {}  # Önden yükleme cache
        self._loading_animation = False
        self._fade_in_progress = False
        
        # JPG izleyici ve otomatik boyutlandırma
        self.jpg_watcher = JPGWatcher(self)
        self.observer = None  # Lazy init - sadece gerektiğinde oluşturulacak
        self.observer_running = False
        
        # Panel genişlik ayarları
        self.sol_panel_genislik = 280
        self.sag_panel_genislik = 320
        self.dragging = None  # Hangi handle sürükleniyor: 'sol' veya 'sag'
        self.drag_start_x = 0
        self.drag_start_genislik = 0
        self.resize_after_id = None  # Throttling için
        
        # Ana layout
        self.grid_columnconfigure(0, weight=0)  # Sol panel - sabit
        self.grid_columnconfigure(1, weight=0)  # Sol handle - sabit
        self.grid_columnconfigure(2, weight=1)  # Orta panel - genişler
        self.grid_columnconfigure(3, weight=0)  # Sağ handle - sabit
        self.grid_columnconfigure(4, weight=0)  # Sağ panel - sabit
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Alt panel için sabit yükseklik
        
        # Sol panel (Klasör listesi ve kontroller)
        self.sol_panel_olustur()
        
        # Sol resize handle
        self.sol_resize_handle_olustur()
        
        # Orta panel (Desen önizleme)
        self.orta_panel_olustur()
        
        # Sağ resize handle
        self.sag_resize_handle_olustur()
        
        # Sağ panel (Bilgi ve etiketler)
        self.sag_panel_olustur()
        
        # Alt panel (Navigasyon)
        self.alt_panel_olustur()

        # Alt imza alanı
        self.grid_rowconfigure(2, weight=0)
        self.imza_olustur()
        
        # Kalıcı ayarları yükle
        self.ayarlari_yukle()
        
        # JPG izleyiciyi başlatma - lazy, sadece klasör seçilince başlayacak
        # self.observer_baslat()  # KALDIRILD - performans için
        
        # Ana klasörler varsa otomatik yükle - Lazy loading için gecikme artırıldı
        self.after(500, self.baslangicta_yukle)
        
    def sol_panel_olustur(self):
        """Sol paneli oluştur - Modern Klasör Listesi ve Kontroller"""
        self.sol_panel = ctk.CTkFrame(
            self, 
            width=self.sol_panel_genislik, 
            corner_radius=12,
            border_width=2,
            border_color="#1f6aa5"
        )
        self.sol_panel.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=10, sticky="nsew")
        # 0: header (logo), 1: scrollable content (klasörler ve arama), 2: alt butonlar
        self.sol_panel.grid_rowconfigure(0, weight=0)  # Logo alanı sabit
        self.sol_panel.grid_rowconfigure(1, weight=1)  # Scroll alanı genişler
        self.sol_panel.grid_rowconfigure(2, weight=0)  # Alt butonlar sabit
        self.sol_panel.grid_columnconfigure(0, weight=1)

        # Başlık + Logo alanı - Modern gradient
        baslik_header = ctk.CTkFrame(
            self.sol_panel, 
            corner_radius=10,
            fg_color="#1f6aa5"
        )
        baslik_header.grid(row=0, column=0, padx=12, pady=(10, 5), sticky="ew")
        baslik_header.grid_columnconfigure(0, weight=1)

        logo_alan = ctk.CTkFrame(
            baslik_header, 
            corner_radius=8, 
            border_width=2, 
            border_color="#4fc3f7"
        )
        logo_alan.grid(row=0, column=0, padx=12, pady=(6, 6), sticky="ew")
        logo_alan.grid_columnconfigure(0, weight=1)
        logo_alan.grid_rowconfigure(1, weight=1)

        # Logo alanı üst çubuk: küçük ikonlu yükle butonu
        ust_cubuk = ctk.CTkFrame(logo_alan, corner_radius=0, fg_color="transparent")
        ust_cubuk.grid(row=0, column=0, padx=4, pady=(2, 0), sticky="ew")
        ust_cubuk.grid_columnconfigure(0, weight=1)

        self.logo_yukle_btn = ctk.CTkButton(
            ust_cubuk,
            text="🖼️",
            width=12,
            height=12,
            command=self.logo_yukle,
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        self.logo_yukle_btn.grid(row=0, column=1, padx=(2, 0), sticky="e")

        # Logo görüntü alanı: tüm genişliğe yayılsın
        self.logo_label = ctk.CTkLabel(
            logo_alan,
            text="Logo yüklenmedi",
            text_color="gray",
            anchor="center",
            height=70
        )
        self.logo_label.grid(row=1, column=0, padx=6, pady=(4, 6), sticky="nsew")
        # Yeniden boyutlandırmada logoyu uyarlamak için - sadece label'ı dinle
        self.logo_label.bind("<Configure>", self._on_logo_area_resize)

        # Sol panel scroll alanı (başlık dışında her şey burada)
        self.sol_scroll = ctk.CTkScrollableFrame(self.sol_panel, corner_radius=8)
        self.sol_scroll.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.sol_scroll.grid_columnconfigure(0, weight=1)

        # Kategori Seçimi Frame - Modern border
        kategori_secim_frame = ctk.CTkFrame(
            self.sol_scroll, 
            corner_radius=10,
            border_width=2,
            border_color="#2196f3"
        )
        kategori_secim_frame.grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        kategori_secim_frame.grid_columnconfigure(0, weight=1)
        
        # Kategori butonları (Desenler / Varyantlar) - Daha modern
        kategori_button_frame = ctk.CTkFrame(kategori_secim_frame, fg_color="transparent")
        kategori_button_frame.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        kategori_button_frame.grid_columnconfigure(0, weight=1)
        kategori_button_frame.grid_columnconfigure(1, weight=1)
        
        self.desenler_btn = ctk.CTkButton(
            kategori_button_frame,
            text="🎨 Desenler",
            command=lambda: self.kategori_sec("Desenler"),
            fg_color="#ff9800",
            hover_color="#fb8c00",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#ff9800"
        )
        self.desenler_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.varyantlar_btn = ctk.CTkButton(
            kategori_button_frame,
            text="🔄 Varyantlar",
            command=lambda: self.kategori_sec("Varyantlar"),
            fg_color="#424242",
            hover_color="#616161",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#424242"
        )
        self.varyantlar_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # Ana Klasör Seç butonu - Modern
        self.klasor_sec_btn = ctk.CTkButton(
            kategori_secim_frame,
            text="📂 Ana Klasör Seç",
            command=self.ana_klasor_sec,
            fg_color="#1f6aa5",
            hover_color="#2196f3",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#1f6aa5"
        )
        self.klasor_sec_btn.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        
        # Durum etiketi (görünmez - sadece kod için)
        self.klasor_durum_label = ctk.CTkLabel(kategori_secim_frame, text="", height=0)
        
        # JPG Boyutlandır butonu - Modern
        self.jpg_boyutlandir_btn = ctk.CTkButton(
            kategori_secim_frame,
            text="🔄 JPG Boyutlandır (1200x900)",
            command=self.ana_klasor_jpgleri_boyutlandir,
            fg_color="#9c27b0",
            hover_color="#ab47bc",
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=2,
            border_color="#9c27b0"
        )
        self.jpg_boyutlandir_btn.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Klasör listesi frame - Modern border
        klasor_frame = ctk.CTkFrame(
            self.sol_scroll, 
            corner_radius=10,
            border_width=2,
            border_color="#2196f3"
        )
        klasor_frame.grid(row=1, column=0, padx=8, pady=6, sticky="nsew")
        klasor_frame.grid_rowconfigure(0, weight=1)
        klasor_frame.grid_columnconfigure(0, weight=1)

        # Scrollable frame - Minimum yükseklik ile daha fazla öğe gösterilir
        self.klasor_listesi = ctk.CTkScrollableFrame(
            klasor_frame,
            corner_radius=8,
            height=450,
            fg_color="transparent"
        )
        self.klasor_listesi.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.klasor_listesi.grid_columnconfigure(0, weight=1)

        # Alt butonlar ve arama frame - sol panelin en altına sabitlendi
        alt_butonlar_frame = ctk.CTkFrame(self.sol_panel, corner_radius=8, fg_color="transparent")
        alt_butonlar_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        alt_butonlar_frame.grid_columnconfigure(0, weight=1)

        # Arama frame (en üstte) - Modern border
        arama_frame = ctk.CTkFrame(
            alt_butonlar_frame, 
            corner_radius=10,
            border_width=2,
            border_color="#4fc3f7"
        )
        arama_frame.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="ew")
        arama_frame.grid_columnconfigure(0, weight=1)

        self.arama_entry = ctk.CTkEntry(
            arama_frame,
            placeholder_text="🔍 Desen veya etiket ara...",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            border_width=2
        )
        self.arama_entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.arama_entry.bind("<KeyRelease>", self.arama_debounce)

        # PDF oluştur butonu - Modern
        self.pdf_btn = ctk.CTkButton(
            alt_butonlar_frame,
            text="📄 PDF Oluştur",
            command=self.pdf_secenekleri_goster,
            fg_color="#1f6aa5",
            hover_color="#2196f3",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#1f6aa5"
        )
        self.pdf_btn.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")

        # Yenile butonu - Modern
        self.yenile_btn = ctk.CTkButton(
            alt_butonlar_frame,
            text="🔄 Yenile",
            command=self.klasoru_yenile,
            fg_color="#4caf50",
            hover_color="#66bb6a",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#4caf50"
        )
        self.yenile_btn.grid(row=2, column=0, padx=8, pady=(0, 6), sticky="ew")

        # Çıkış butonu - Modern
        self.cikis_btn = ctk.CTkButton(
            alt_butonlar_frame,
            text="❌ Çıkış",
            command=self.cikis_yap,
            fg_color="#f44336",
            hover_color="#ef5350",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            border_width=2,
            border_color="#f44336"
        )
        self.cikis_btn.grid(row=3, column=0, padx=8, pady=0, sticky="ew")
    
    def sol_resize_handle_olustur(self):
        """Sol panel ile orta panel arasında sürüklenebilir ayırıcı"""
        self.sol_handle = ctk.CTkFrame(self, width=5, corner_radius=0, fg_color="transparent", 
                                       cursor="sb_h_double_arrow")
        self.sol_handle.grid(row=0, column=1, rowspan=2, pady=10, sticky="ns")
        
        # Mouse event'leri
        self.sol_handle.bind("<Button-1>", lambda e: self.basla_resize(e, 'sol'))
        self.sol_handle.bind("<B1-Motion>", lambda e: None)  # Motion'da hiçbir şey yapma
        self.sol_handle.bind("<ButtonRelease-1>", self.bitir_resize)
        self.sol_handle.bind("<Enter>", lambda e: self.sol_handle.configure(fg_color="#3a3a3a"))
        self.sol_handle.bind("<Leave>", lambda e: self.sol_handle.configure(fg_color="transparent"))
    
    def sag_resize_handle_olustur(self):
        """Orta panel ile sağ panel arasında sürüklenebilir ayırıcı"""
        self.sag_handle = ctk.CTkFrame(self, width=5, corner_radius=0, fg_color="transparent",
                                       cursor="sb_h_double_arrow")
        self.sag_handle.grid(row=0, column=3, rowspan=2, pady=10, sticky="ns")
        
        # Mouse event'leri
        self.sag_handle.bind("<Button-1>", lambda e: self.basla_resize(e, 'sag'))
        self.sag_handle.bind("<B1-Motion>", lambda e: None)  # Motion'da hiçbir şey yapma
        self.sag_handle.bind("<ButtonRelease-1>", self.bitir_resize)
        self.sag_handle.bind("<Enter>", lambda e: self.sag_handle.configure(fg_color="#3a3a3a"))
        self.sag_handle.bind("<Leave>", lambda e: self.sag_handle.configure(fg_color="transparent"))
    
    def basla_resize(self, event, taraf):
        """Resize işlemini başlat"""
        self.dragging = taraf
        self.drag_start_x = event.x_root
        if taraf == 'sol':
            self.drag_start_genislik = self.sol_panel_genislik
        else:
            self.drag_start_genislik = self.sag_panel_genislik
    
    def bitir_resize(self, event):
        """Resize işlemi bitti - SADECE BURADA güncelle"""
        if not self.dragging:
            return
        
        delta = event.x_root - self.drag_start_x
        
        if self.dragging == 'sol':
            yeni_genislik = max(200, min(600, self.drag_start_genislik + delta))
            self.sol_panel_genislik = yeni_genislik
            self.sol_panel.configure(width=yeni_genislik)
        else:
            yeni_genislik = max(250, min(700, self.drag_start_genislik - delta))
            self.sag_panel_genislik = yeni_genislik
            self.sag_panel.configure(width=yeni_genislik)
        
        self.dragging = None
        
    def orta_panel_olustur(self):
        """Orta paneli oluştur - Desen önizleme"""
        self.orta_panel = ctk.CTkFrame(self, corner_radius=10)
        self.orta_panel.grid(row=0, column=2, padx=5, pady=10, sticky="nsew")
        self.orta_panel.grid_rowconfigure(1, weight=1)
        self.orta_panel.grid_columnconfigure(0, weight=1)
        
        # Başlık frame
        baslik_frame = ctk.CTkFrame(self.orta_panel, height=60, corner_radius=8)
        baslik_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        baslik_frame.grid_columnconfigure(0, weight=1)
        
        self.desen_baslik = ctk.CTkLabel(
            baslik_frame,
            text="🧵 Desen Önizleme",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#E0E0E0"
        )
        self.desen_baslik.grid(row=0, column=0, padx=20, pady=(14, 8), sticky="w")
        # İnce ayraç çizgisi
        baslik_ayrac = ctk.CTkFrame(baslik_frame, height=1, fg_color="#2b2b2b")
        baslik_ayrac.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")
        
        # Önizleme frame - Modern görünüm için gradient efekti simülasyonu
        self.onizleme_frame = ctk.CTkFrame(
            self.orta_panel, 
            corner_radius=12,
            border_width=2,
            border_color="#1f6aa5"
        )
        self.onizleme_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="nsew")
        self.onizleme_frame.grid_rowconfigure(0, weight=1)
        self.onizleme_frame.grid_columnconfigure(0, weight=1)
        
        # Desen label - yükleme durumu için yer tutucu
        self.desen_label = ctk.CTkLabel(
            self.onizleme_frame,
            text="",
            font=ctk.CTkFont(size=16)
        )
        self.desen_label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        # Yükleme göstergesi (spinner)
        self.loading_label = ctk.CTkLabel(
            self.onizleme_frame,
            text="⏳ Yükleniyor...",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#1f6aa5"
        )
        # Başlangıçta gizli
        
        # Boş durum mesajı
        self.bos_durum_label = ctk.CTkLabel(
            self.onizleme_frame,
            text="📁 Bir klasör seçin ve desenler yüklensin\n\n💡 İpucu: Sol panelden bir klasör seçin",
            font=ctk.CTkFont(size=14),
            text_color="gray",
            justify="center"
        )
        self.bos_durum_label.grid(row=0, column=0, padx=20, pady=20)

        # İmza (overlay) kaldırıldı - istek üzerine

        # Önizleme alanı yeniden boyutlandığında görseli alana sığdır
        self._preview_resize_job = None
        self.onizleme_frame.bind("<Configure>", self._on_preview_area_resize)
        
        # Klavye kısayolları
        self.bind("<Left>", lambda e: self.onceki_desen())
        self.bind("<Right>", lambda e: self.sonraki_desen())
        self.bind("<f>", lambda e: self.tam_ekran_goster())
        self.bind("<F>", lambda e: self.tam_ekran_goster())
        
        # Mouse scroll wheel ile zoom (Ctrl tuşu ile birlikte)
        self.desen_label.bind("<Control-MouseWheel>", self._onizleme_zoom)  # Windows
        self.desen_label.bind("<Control-Button-4>", self._onizleme_zoom)  # Linux scroll up
        self.desen_label.bind("<Control-Button-5>", self._onizleme_zoom)  # Linux scroll down
        
        # Normal scroll'u engelle
        self.desen_label.bind("<MouseWheel>", self._onizleme_scroll_stop)  # Windows
        self.desen_label.bind("<Button-4>", self._onizleme_scroll_stop)  # Linux scroll up
        self.desen_label.bind("<Button-5>", self._onizleme_scroll_stop)  # Linux scroll down
        
        # Çift tıklama ile tam ekran
        self.desen_label.bind("<Double-Button-1>", lambda e: self.tam_ekran_goster())
        
        # Sağ tık ile zoom sıfırla
        self.desen_label.bind("<Button-3>", lambda e: self._zoom_sifirla())
        
        # Dosya bilgisi label - Modern ikonlar ve renklerle
        self.dosya_bilgi = ctk.CTkLabel(
            self.orta_panel,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4fc3f7"
        )
        self.dosya_bilgi.grid(row=2, column=0, padx=20, pady=(0, 10))
        
        # Tam ekran butonu - Hover efekti için özel renkler
        self.tam_ekran_btn = ctk.CTkButton(
            self.orta_panel,
            text="🖼️ Tam Ekran (Çift Tıkla veya F)",
            command=self.tam_ekran_goster,
            fg_color="#1f6aa5",
            hover_color="#2196f3",
            height=45,
            corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"),
            border_width=2,
            border_color="#1f6aa5"
        )
        self.tam_ekran_btn.grid(row=3, column=0, padx=20, pady=(0, 20))
        
    def sag_panel_olustur(self):
        """Sağ paneli oluştur - Modern Etiket Yönetimi"""
        self.sag_panel = ctk.CTkFrame(
            self, 
            width=self.sag_panel_genislik, 
            corner_radius=12,
            border_width=2,
            border_color="#1f6aa5"
        )
        self.sag_panel.grid(row=0, column=4, rowspan=2, padx=(5, 10), pady=10, sticky="nsew")
        self.sag_panel.grid_rowconfigure(2, weight=1)
        self.sag_panel.grid_columnconfigure(0, weight=1)
        
        # Başlık - Modern gradient efekti
        baslik_frame = ctk.CTkFrame(
            self.sag_panel,
            corner_radius=10,
            fg_color="#1f6aa5"
        )
        baslik_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        
        baslik = ctk.CTkLabel(
            baslik_frame,
            text="🏷️ Etiket Yönetimi",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white"
        )
        baslik.pack(pady=12)
        
        # Etiket ekleme frame - Modern tasarım
        etiket_ekle_frame = ctk.CTkFrame(
            self.sag_panel, 
            corner_radius=10,
            border_width=2,
            border_color="#2196f3"
        )
        etiket_ekle_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        etiket_ekle_frame.grid_columnconfigure(0, weight=1)
        
        etiket_label = ctk.CTkLabel(
            etiket_ekle_frame,
            text="✨ Yeni Etiket Ekle",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#4fc3f7"
        )
        etiket_label.grid(row=0, column=0, padx=12, pady=(12, 5), sticky="w")
        
        self.etiket_entry = ctk.CTkEntry(
            etiket_ekle_frame,
            placeholder_text="🔖 Etiket adı girin...",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            border_width=2
        )
        self.etiket_entry.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        
        # Enter tuşu ile ekleme
        self.etiket_entry.bind("<Return>", lambda e: self.etiket_ekle())
        
        self.etiket_ekle_btn = ctk.CTkButton(
            etiket_ekle_frame,
            text="➕ Ekle (Enter)",
            command=self.etiket_ekle,
            fg_color="#4caf50",
            hover_color="#66bb6a",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            border_width=2,
            border_color="#4caf50"
        )
        self.etiket_ekle_btn.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        
        
        
        # Mevcut etiketler frame - Modern scrollable + combobox
        etiketler_frame = ctk.CTkFrame(
            self.sag_panel, 
            corner_radius=10,
            border_width=2,
            border_color="#2196f3"
        )
        etiketler_frame.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")
        etiketler_frame.grid_rowconfigure(2, weight=1)
        etiketler_frame.grid_columnconfigure(0, weight=1)
        etiketler_frame.grid_columnconfigure(1, weight=0)

        etiketler_baslik = ctk.CTkLabel(
            etiketler_frame,
            text="📑 Mevcut Etiketler",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#4fc3f7"
        )
        etiketler_baslik.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        # Tüm etiketleri gösteren combobox (şık görünüm)
        try:
            _tum_etik_orj = self.get_tum_etiketler()
        except Exception:
            _tum_etik_orj = []
        _tum_etik_pretty = [self.format_etiket_gorunumu(e) for e in _tum_etik_orj]
        self._tum_etiket_map = {p: o for p, o in zip(_tum_etik_pretty, _tum_etik_orj)}
        self.tum_etiketler_combo = ctk.CTkComboBox(
            etiketler_frame,
            values=_tum_etik_pretty,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e0f7fa",
            corner_radius=8,
            border_width=2,
            border_color="#2196f3",
            button_color="#1976d2",
            button_hover_color="#42a5f5",
            dropdown_fg_color="#0b1a26",
            dropdown_text_color="#e3f2fd",
            dropdown_font=ctk.CTkFont(size=13)
        )
        self.tum_etiketler_combo.grid(row=1, column=0, padx=(12, 6), pady=(0, 8), sticky="ew")
        # Enter ile arama yapmayı bağla
        try:
            self.tum_etiketler_combo.bind("<Return>", self.tum_etiket_git)
        except Exception:
            pass

        # Git butonu
        self.tum_etiket_git_btn = ctk.CTkButton(
            etiketler_frame,
            text="➡️",
            width=42,
            height=36,
            command=self.tum_etiket_git,
            fg_color="#1976d2",
            hover_color="#42a5f5",
            corner_radius=8,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.tum_etiket_git_btn.grid(row=1, column=1, padx=(0, 12), pady=(0, 8))
        # Başlangıçta metni boş bırak
        try:
            self.tum_etiketler_combo.set("")
        except Exception:
            pass

        self.etiketler_listesi = ctk.CTkScrollableFrame(
            etiketler_frame,
            corner_radius=8,
            fg_color="transparent"
        )
        self.etiketler_listesi.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.etiketler_listesi.grid_columnconfigure(0, weight=1)
        
        # İstatistikler frame - Gradient efekti
        istatistik_frame = ctk.CTkFrame(
            self.sag_panel, 
            corner_radius=10,
            fg_color="#1f6aa5"
        )
        istatistik_frame.grid(row=3, column=0, padx=15, pady=(10, 15), sticky="ew")
        
        istatistik_baslik = ctk.CTkLabel(
            istatistik_frame,
            text="📊 İstatistikler",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="white"
        )
        istatistik_baslik.grid(row=0, column=0, padx=12, pady=(12, 5), sticky="w")
        
        # Simetrik istatistik yerleşimi (3 satır, 3 sütun: ikon | başlık | değer)
        stats_grid = ctk.CTkFrame(istatistik_frame, fg_color="transparent")
        stats_grid.grid(row=1, column=0, padx=8, pady=(0, 10), sticky="ew")
        stats_grid.grid_columnconfigure(0, weight=0)  # ikon
        stats_grid.grid_columnconfigure(1, weight=1)  # başlık
        stats_grid.grid_columnconfigure(2, weight=0)  # değer

        # Klasör
        ctk.CTkLabel(stats_grid, text="📁", text_color="white").grid(row=0, column=0, padx=(6, 6), pady=4, sticky="w")
        ctk.CTkLabel(stats_grid, text="Klasör:", font=ctk.CTkFont(size=12, weight="normal"), text_color="#e0e0e0", anchor="w").grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.stat_klasor_value = ctk.CTkLabel(stats_grid, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color="#ffd600", anchor="e")
        self.stat_klasor_value.grid(row=0, column=2, padx=(6, 10), pady=4, sticky="e")

        # Desen
        ctk.CTkLabel(stats_grid, text="🎨", text_color="white").grid(row=1, column=0, padx=(6, 6), pady=4, sticky="w")
        ctk.CTkLabel(stats_grid, text="Desen:", font=ctk.CTkFont(size=12, weight="normal"), text_color="#e0e0e0", anchor="w").grid(row=1, column=1, padx=6, pady=4, sticky="w")
        self.stat_desen_value = ctk.CTkLabel(stats_grid, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color="#4fc3f7", anchor="e")
        self.stat_desen_value.grid(row=1, column=2, padx=(6, 10), pady=4, sticky="e")

        # Etiketli
        ctk.CTkLabel(stats_grid, text="🏷️", text_color="white").grid(row=2, column=0, padx=(6, 6), pady=4, sticky="w")
        ctk.CTkLabel(stats_grid, text="Etiketli:", font=ctk.CTkFont(size=12, weight="normal"), text_color="#e0e0e0", anchor="w").grid(row=2, column=1, padx=6, pady=4, sticky="w")
        self.stat_etiketli_value = ctk.CTkLabel(stats_grid, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color="#ff4081", anchor="e")
        self.stat_etiketli_value.grid(row=2, column=2, padx=(6, 10), pady=4, sticky="e")
    
    def istatistikleri_guncelle(self):
        """İstatistikleri güncelle - Modern ikonlarla"""
        toplam_klasor = len(self.desenler) + len(self.varyantlar)
        toplam_desen = sum(len(desenler) for desenler in self.desenler.values()) + \
                      sum(len(desenler) for desenler in self.varyantlar.values())
        etiketli_desen = sum(
            1 for desenler in self.desenler.values()
            for desen in desenler
            if desen['etiketler']
        ) + sum(
            1 for desenler in self.varyantlar.values()
            for desen in desenler
            if desen['etiketler']
        )
        # Değerleri ayrı etiketlere yazarak simetriyi koru
        try:
            self.stat_klasor_value.configure(text=str(toplam_klasor))
            self.stat_desen_value.configure(text=str(toplam_desen))
            self.stat_etiketli_value.configure(text=str(etiketli_desen))
        except Exception:
            pass

    def get_tum_etiketler(self):
        """Desenler ve Varyantlar içindeki TÜM benzersiz etiketleri topla"""
        tum = set()
        try:
            for desenler in self.desenler.values():
                for d in desenler:
                    for e in d.get('etiketler', []):
                        if isinstance(e, str):
                            tum.add(e.strip())
        except Exception:
            pass
        try:
            for desenler in self.varyantlar.values():
                for d in desenler:
                    for e in d.get('etiketler', []):
                        if isinstance(e, str):
                            tum.add(e.strip())
        except Exception:
            pass
        return sorted(tum)

    def format_etiket_gorunumu(self, etiket: str) -> str:
        """Combobox'ta gösterilecek şık etiket metni üret."""
        if not isinstance(etiket, str):
            return ""
        t = etiket.strip()
        # Küçük düzenlemeler: alt çizgiyi boşluk yap, çok uzun ise kısalt
        t = t.replace('_', ' ').replace('-', ' ')
        if len(t) > 24:
            t = t[:22] + "…"
        return f"🏷️ {t.upper()}"

    def desen_numarasini_cikar(self, ad: str) -> str:
        """Dosya adından desen numarasını çıkar (ilk 3+ haneli sayı)."""
        try:
            import re, os
            isim = os.path.splitext(ad)[0]
            m = re.search(r"(\d{3,})", isim)
            return m.group(1) if m else ""
        except Exception:
            return ""

    def olustur_search_text(self, ad: str, etiketler: list) -> str:
        """Aramada hızlı karşılaştırma için birleşik metin üret (küçük harf)."""
        try:
            import os
            isim = os.path.splitext(ad)[0]
            parcalar = [isim]
            numara = self.desen_numarasini_cikar(ad)
            if numara:
                parcalar.append(numara)
            if etiketler:
                parcalar.extend(etiketler)
            return " ".join(parcalar).lower()
        except Exception:
            return (ad or "").lower()

    def tum_etiket_git(self, event=None):
        """Sağdaki etiket combobox'ından seçili etiketle arama yap."""
        try:
            secim = (self.tum_etiketler_combo.get() or "").strip()
        except Exception:
            secim = ""
        if not secim:
            return
        # Pretty'den orijinale dönüştür
        orj = None
        try:
            if hasattr(self, "_tum_etiket_map"):
                orj = self._tum_etiket_map.get(secim)
        except Exception:
            orj = None
        if not orj:
            # Fallback: doğrudan kullan
            orj = secim.replace("🏷️", "").strip()
        # Arama kutusuna yaz ve ara
        try:
            self.arama_entry.delete(0, 'end')
            self.arama_entry.insert(0, orj)
        except Exception:
            pass
        self.arama_yap()

    
        
    def alt_panel_olustur(self):
        """Alt paneli oluştur - Navigasyon"""
        self.alt_panel = ctk.CTkFrame(self, height=100, corner_radius=10)
        self.alt_panel.grid(row=1, column=2, padx=5, pady=(0, 10), sticky="ew")
        self.alt_panel.grid_columnconfigure(1, weight=1)
        
        # Önceki butonu - Modern görünüm
        self.onceki_btn = ctk.CTkButton(
            self.alt_panel,
            text="⬅️ Önceki (←)",
            command=self.onceki_desen,
            fg_color="#1f6aa5",
            hover_color="#2196f3",
            width=160,
            height=55,
            corner_radius=10,
            font=ctk.CTkFont(size=16, weight="bold"),
            border_width=2,
            border_color="#1f6aa5"
        )
        self.onceki_btn.grid(row=0, column=0, padx=20, pady=20)
        
        # Pozisyon label - Daha belirgin
        self.pozisyon_label = ctk.CTkLabel(
            self.alt_panel,
            text="0 / 0",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#4fc3f7"
        )
        self.pozisyon_label.grid(row=0, column=1, padx=20, pady=20)
        
        # Sonraki butonu - Modern görünüm
        self.sonraki_btn = ctk.CTkButton(
            self.alt_panel,
            text="Sonraki (→) ➡️",
            command=self.sonraki_desen,
            fg_color="#1f6aa5",
            hover_color="#2196f3",
            width=160,
            height=55,
            corner_radius=10,
            font=ctk.CTkFont(size=16, weight="bold"),
            border_width=2,
            border_color="#1f6aa5"
        )
        self.sonraki_btn.grid(row=0, column=2, padx=20, pady=20)
    
    def imza_olustur(self):
        """Ana pencerenin en altına merkezde imza etiketi ekle"""
        try:
            self.imza_label = ctk.CTkLabel(
                self,
                text="DESIGNED BY Murteza ALEMDAR",
                text_color="#888888",
                font=ctk.CTkFont(size=11, slant="italic")
            )
            # En alt satırda tüm sütunlara yayılacak şekilde ortala
            self.imza_label.grid(row=2, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="ew")
        except Exception as e:
            print(f"Imza oluşturulurken hata: {e}")
        
    def klasoru_yenile(self):
        """Klasörü yeniden tara ve güncelle"""
        if not self.ana_klasor:
            messagebox.showwarning("Uyarı", "Lütfen önce bir klasör seçin")
            return
        
        # Cache'i temizle (yeniden tarama için)
        if self.cache_dosyasi and self.cache_dosyasi.exists():
            try:
                self.cache_dosyasi.unlink()
                print("Cache temizlendi, yeniden taranıyor...")
            except Exception as e:
                print(f"Cache temizleme hatası: {e}")
        
        # Mevcut pozisyonu kaydet
        aktif_klasor_gecici = self.aktif_klasor
        aktif_index_gecici = self.aktif_desen_index
        
        # Klasörü yeniden yükle
        self.klasoru_yukle()
        
        # Eğer aktif klasör hala varsa, pozisyonu geri yükle
        if aktif_klasor_gecici and aktif_klasor_gecici in self.desenler:
            self.aktif_klasor = aktif_klasor_gecici
            # Index sınırları içinde mi kontrol et
            if aktif_index_gecici < len(self.desenler[aktif_klasor_gecici]):
                self.aktif_desen_index = aktif_index_gecici
            else:
                self.aktif_desen_index = 0
            self.deseni_goster()
        
        messagebox.showinfo("Başarılı", "Klasör içeriği güncellendi!")
    
    def ana_klasor_sec(self):
        """Aktif kategoriye göre ana klasör seç"""
        kategori = self.aktif_kategori
        klasor = filedialog.askdirectory(title=f"{kategori} Ana Klasörünü Seçin")
        if not klasor:
            return
        
        klasor_path = Path(klasor)
        
        if kategori == "Desenler":
            self.desenler_ana_klasor = klasor_path
            self.desenler_etiketler_dosyasi = klasor_path / "etiketler.json"
            self.desenler_ayarlar_dosyasi = klasor_path / ".desenler_ayarlar.json"
            self.desenler_cache_dosyasi = klasor_path / ".desenler_cache.json"
            
            # Ana klasör yolunu kaydet
            try:
                desenler_dosyasi = UYGULAMA_KLASORU / "desenler_ana_klasor.txt"
                with open(desenler_dosyasi, 'w', encoding='utf-8') as f:
                    f.write(str(klasor_path))
            except Exception as e:
                print(f"Desenler ana klasör yolu kaydedilemedi: {e}")
            
        else:  # Varyantlar
            self.varyantlar_ana_klasor = klasor_path
            self.varyantlar_etiketler_dosyasi = klasor_path / "etiketler.json"
            self.varyantlar_ayarlar_dosyasi = klasor_path / ".varyantlar_ayarlar.json"
            self.varyantlar_cache_dosyasi = klasor_path / ".varyantlar_cache.json"
            
            # Ana klasör yolunu kaydet
            try:
                varyantlar_dosyasi = UYGULAMA_KLASORU / "varyantlar_ana_klasor.txt"
                with open(varyantlar_dosyasi, 'w', encoding='utf-8') as f:
                    f.write(str(klasor_path))
            except Exception as e:
                print(f"Varyantlar ana klasör yolu kaydedilemedi: {e}")
        
        # Durum label'ını güncelle
        klasor_adi = klasor_path.name
        if len(klasor_adi) > 30:
            klasor_adi = klasor_adi[:27] + "..."
        
        kategori_emoji = "🎨" if kategori == "Desenler" else "🔄"
        self.klasor_durum_label.configure(
            text=f"✅ {kategori_emoji} {klasor_adi}",
            text_color="#4caf50"
        )
        
        # Observer'ı başlat (yeni klasörü izle)
        self.observer_baslat()
        
        # Klasör içindeki ayarları yükle ve desenileri tara
        self.klasor_ayarlarini_yukle(kategori)
        self.klasoru_yukle(kategori)
    
    def logo_yukle(self):
        """Başlığa yerleştirilecek logoyu seç ve göster"""
        dosya_turu = [
            ("Görüntü Dosyaları", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
            ("Tüm Dosyalar", "*.*")
        ]
        yol = filedialog.askopenfilename(title="Logo Seç", filetypes=dosya_turu)
        if not yol:
            return
        try:
            self.logo_yolu = yol
            self.logo_goster(yol)
            self.ayarlari_kaydet()
        except Exception as e:
            messagebox.showerror("Hata", f"Logo yüklenemedi: {e}")
    
    def logo_goster(self, yol: str):
        """Seçili logoyu ölçekleyip başlık alanında göster"""
        if not hasattr(self, 'logo_label'):
            return
        try:
            # Orijinal resmi cache'le
            self._logo_pil_image = Image.open(yol).convert("RGBA")
            # Alan boyutunu al (başlatma anında 1 olabilir)
            hedef_w = max(1, self.logo_label.winfo_width())
            hedef_h = max(1, self.logo_label.winfo_height())
            if hedef_w <= 1 or hedef_h <= 1:
                # İlk yüklemede makul bir hedef kullan
                hedef_w, hedef_h = 360, 110
            self._apply_logo_cover(hedef_w, hedef_h)
        except Exception as e:
            print(f"Logo gösterilemedi: {e}")

    def _on_logo_area_resize(self, event):
        """Logo alanı yeniden boyutlanınca logoyu yeniden ölçekle"""
        try:
            if self._logo_pil_image is None or not hasattr(self, 'logo_label'):
                return
            # Event'ten gelen boyutu kullan, ancak çok küçük değerler için label'ın gerçek boyutunu al
            hedef_w = max(1, int(getattr(event, 'width', 1)))
            hedef_h = max(1, int(getattr(event, 'height', 1)))
            if hedef_w <= 1 or hedef_h <= 1:
                hedef_w = max(1, self.logo_label.winfo_width())
                hedef_h = max(1, self.logo_label.winfo_height())
            # Aynı boyutta ise tekrar işlem yapma
            if self._last_logo_size == (hedef_w, hedef_h):
                return
            # Debounce: var olan işi iptal et ve kısa bir gecikme ile uygula
            if self._logo_resize_job is not None:
                try:
                    self.after_cancel(self._logo_resize_job)
                except Exception:
                    pass
            def _do_resize():
                try:
                    if not hasattr(self, 'logo_label') or not self.logo_label.winfo_exists():
                        return
                    self._last_logo_size = (hedef_w, hedef_h)
                    self._apply_logo_cover(hedef_w, hedef_h)
                except Exception as e:
                    print(f"Logo resize içinde hata: {e}")
                finally:
                    self._logo_resize_job = None
            self._logo_resize_job = self.after(100, _do_resize)
        except Exception as e:
            print(f"Logo yeniden boyutlandırma hatası: {e}")

    def _apply_logo_cover(self, hedef_w: int, hedef_h: int):
        """Logo görselini alanı tam kaplayacak şekilde ölçekle ve ortalayarak kırp."""
        try:
            if self._logo_pil_image is None:
                return
            w, h = self._logo_pil_image.size
            # KAPLA (cover): Alanı doldurmak için büyük oranı kullan
            oran = max(hedef_w / w, hedef_h / h)
            yeni_w = max(1, int(w * oran))
            yeni_h = max(1, int(h * oran))
            img_resized = self._logo_pil_image.resize((yeni_w, yeni_h), Image.LANCZOS)
            # Ortadan kırparak hedefe indir
            sol = max(0, (yeni_w - hedef_w) // 2)
            ust = max(0, (yeni_h - hedef_h) // 2)
            sag = sol + hedef_w
            alt = ust + hedef_h
            img_cropped = img_resized.crop((sol, ust, sag, alt))
            self._logo_ctk_image = ctk.CTkImage(light_image=img_cropped, size=(hedef_w, hedef_h))
            self.logo_label.configure(image=self._logo_ctk_image, text="")
        except Exception as e:
            print(f"Logo kaplama uygulanırken hata: {e}")
        
    def klasoru_yukle(self, kategori):
        """Klasör içeriğini yükle - kategori bazlı"""
        ana_klasor = self.desenler_ana_klasor if kategori == "Desenler" else self.varyantlar_ana_klasor
        
        if not ana_klasor or not ana_klasor.exists():
            return
        
        # Etiketleri yükle
        self.etiketleri_yukle(kategori)
        
        # Alt klasörleri tara
        self.alt_klasorleri_yukle(kategori)
        
        # Klasör listesini güncelle
        self.klasor_listesini_guncelle()
        
        # İstatistikleri güncelle
        self.istatistikleri_guncelle()
    
    def baslangicta_yukle(self):
        """Başlangıçta hızlı yükleme: önce cache'den, sonra arkaplanda tam tarama"""
        import threading
        
        aktif_kategori = self.aktif_kategori  # "Desenler" varsayılan
        diger_kategori = "Varyantlar" if aktif_kategori == "Desenler" else "Desenler"
        
        # 1) Hızlı açılış: aktif kategori için cache'den yükle (varsa)
        self.cacheten_yukle(aktif_kategori)
        self.klasor_listesini_guncelle()
        
        # 2) Aktif kategori için tam taramayı arkaplanda başlat
        self.taramayi_arkaplanda_baslat(aktif_kategori)
        
        # 3) Diğer kategoriyi biraz gecikmeli arkaplanda tara (UI açıldıktan sonra)
        def _gecikmeli():
            self.taramayi_arkaplanda_baslat(diger_kategori)
        self.after(1500, _gecikmeli)
        
        # 4) İlk deseni göster (varsa)
        if self.aktif_klasor:
            self.deseni_goster()

    def cacheten_yukle(self, kategori):
        """Kategori için cache dosyasından hızlı yükleme yap (varsa)"""
        try:
            cache_dosyasi = self.desenler_cache_dosyasi if kategori == "Desenler" else self.varyantlar_cache_dosyasi
            if not cache_dosyasi or not Path(cache_dosyasi).exists():
                return
            with open(cache_dosyasi, 'r', encoding='utf-8') as f:
                data = json.load(f)
            desenler_dict = {}
            for klasor_adi, liste in data.get('desenler', {}).items():
                desenler_dict[klasor_adi] = [
                    {
                        'dosya': Path(item['dosya']),
                        'ad': item['ad'],
                        'boyut': item.get('boyut', 0),
                        'etiketler': item.get('etiketler', []),
                        'numara': item.get('numara') or self.desen_numarasini_cikar(item.get('ad', '')),
                        'search_text': self.olustur_search_text(item.get('ad', ''), item.get('etiketler', []))
                    }
                    for item in liste
                ]
            if kategori == "Desenler":
                self.desenler = desenler_dict
            else:
                self.varyantlar = desenler_dict
            print(f"⚡ {kategori} cache'den yüklendi: {len(desenler_dict)} klasör")
        except Exception as e:
            print(f"{kategori} cache yükleme hatası: {e}")

    def taramayi_arkaplanda_baslat(self, kategori):
        """Alt klasör taramasını ana thread'i bloklamadan çalıştır"""
        import threading
        
        ana_klasor = self.desenler_ana_klasor if kategori == "Desenler" else self.varyantlar_ana_klasor
        if not ana_klasor or not Path(ana_klasor).exists():
            return
        
        def _is():
            # Ağ/disk taraması burada yapılır
            self.alt_klasorleri_yukle(kategori)
            # Cache'e yaz
            self.cache_kaydet(kategori)
            # UI güncellemesi ana thread'de
            self.after(0, self._tarama_bitti_ui_guncelle, kategori)
        
        threading.Thread(target=_is, daemon=True).start()
    
    def _tarama_bitti_ui_guncelle(self, kategori):
        """Taramadan sonra UI'ı uygun şekilde yenile"""
        # Sadece ilgili kategorideysek listeyi yenile; değilsek de sayıları güncelle
        if self.aktif_kategori == kategori:
            self.klasor_listesini_guncelle()
            # Varsayılan seçim korunur; seçili klasör yoksa ilkini seçebiliriz
            aktif_desenler = self.get_aktif_kategori_desenler()
            if aktif_desenler and (not self.aktif_klasor or self.aktif_klasor not in aktif_desenler):
                ilk_klasor = list(aktif_desenler.keys())[0]
                self.klasor_sec_desen(ilk_klasor)
        # İstatistikleri güncelle
        self.istatistikleri_guncelle()
    
    def ayarlari_kaydet(self):
        """Ayarları her iki kategorinin dosyasına da kaydet"""
        try:
            ayarlar = {
                'son_klasor': self.aktif_klasor,
                'son_index': self.aktif_desen_index,
                'logo_yolu': self.logo_yolu,
                'sol_panel_genislik': self.sol_panel_genislik,
                'sag_panel_genislik': self.sag_panel_genislik
            }
            
            # Desenler ayarlarını kaydet
            if self.desenler_ana_klasor and self.desenler_ayarlar_dosyasi:
                with open(self.desenler_ayarlar_dosyasi, 'w', encoding='utf-8') as f:
                    json.dump(ayarlar, f, ensure_ascii=False, indent=2)
            
            # Varyantlar ayarlarını kaydet
            if self.varyantlar_ana_klasor and self.varyantlar_ayarlar_dosyasi:
                with open(self.varyantlar_ayarlar_dosyasi, 'w', encoding='utf-8') as f:
                    json.dump(ayarlar, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ayarlar kaydedilemedi: {str(e)}")
            
    def ayarlari_yukle(self):
        """Kaydedilmiş ana klasör yollarını yükle - uygulama klasöründen"""
        try:
            # DEFAULT YOLLAR
            default_desenler_yolu = r"\\192.168.1.36\TasarımVeSablonuOlanDesenler\Karakoç Tasarımlar"
            default_varyantlar_yolu = r"\\192.168.1.36\TasarımVeSablonuOlanDesenler\VARYANT - Şablonu Olan Desenler"
            default_logo_yolu = r"\\192.168.1.36\Uygulamalar\LOGO\DuvarKagidi.jpg"
            
            # Desenler ana klasörünü yükle
            desenler_dosyasi = UYGULAMA_KLASORU / "desenler_ana_klasor.txt"
            if desenler_dosyasi.exists():
                with open(desenler_dosyasi, 'r', encoding='utf-8') as f:
                    yol = f.read().strip()
            else:
                # Default yol kullan
                yol = default_desenler_yolu
                
            path = Path(yol)
            if path.exists() and path.is_dir():
                self.desenler_ana_klasor = path
                self.desenler_etiketler_dosyasi = path / "etiketler.json"
                self.desenler_ayarlar_dosyasi = path / ".desenler_ayarlar.json"
                self.desenler_cache_dosyasi = path / ".desenler_cache.json"
                
                # Klasör ayarlarını yükle
                self.klasor_ayarlarini_yukle("Desenler")
            
            # Varyantlar ana klasörünü yükle
            varyantlar_dosyasi = UYGULAMA_KLASORU / "varyantlar_ana_klasor.txt"
            if varyantlar_dosyasi.exists():
                with open(varyantlar_dosyasi, 'r', encoding='utf-8') as f:
                    yol = f.read().strip()
            else:
                # Default yol kullan
                yol = default_varyantlar_yolu
                
            path = Path(yol)
            if path.exists() and path.is_dir():
                self.varyantlar_ana_klasor = path
                self.varyantlar_etiketler_dosyasi = path / "etiketler.json"
                self.varyantlar_ayarlar_dosyasi = path / ".varyantlar_ayarlar.json"
                self.varyantlar_cache_dosyasi = path / ".varyantlar_cache.json"
                
                # Klasör ayarlarını yükle
                self.klasor_ayarlarini_yukle("Varyantlar")
            
            # Default logo yükle (eğer henüz yüklenmediyse)
            if not self.logo_yolu and Path(default_logo_yolu).exists():
                self.logo_yolu = default_logo_yolu
                try:
                    self.logo_goster(self.logo_yolu)
                except Exception as e:
                    print(f"Default logo yüklenemedi: {e}")
            
            # Durum label'ını güncelle
            self.durum_label_guncelle()
        except Exception as e:
            print(f"Ana klasör yolları yüklenemedi: {str(e)}")
    
    def durum_label_guncelle(self):
        """Aktif kategoriye göre durum label'ını güncelle"""
        if self.aktif_kategori == "Desenler" and self.desenler_ana_klasor:
            klasor_adi = self.desenler_ana_klasor.name
            if len(klasor_adi) > 30:
                klasor_adi = klasor_adi[:27] + "..."
            self.klasor_durum_label.configure(
                text=f"✅ 🎨 {klasor_adi}",
                text_color="#4caf50"
            )
        elif self.aktif_kategori == "Varyantlar" and self.varyantlar_ana_klasor:
            klasor_adi = self.varyantlar_ana_klasor.name
            if len(klasor_adi) > 30:
                klasor_adi = klasor_adi[:27] + "..."
            self.klasor_durum_label.configure(
                text=f"✅ 🔄 {klasor_adi}",
                text_color="#4caf50"
            )
        else:
            self.klasor_durum_label.configure(
                text="Kategori seçin ve klasör belirleyin",
                text_color="gray"
            )
    
    def klasor_ayarlarini_yukle(self, kategori):
        """Ana klasör içindeki ayarlar dosyasını yükle - kategori bazlı"""
        ayarlar_dosyasi = self.desenler_ayarlar_dosyasi if kategori == "Desenler" else self.varyantlar_ayarlar_dosyasi
        
        try:
            if ayarlar_dosyasi and ayarlar_dosyasi.exists():
                with open(ayarlar_dosyasi, 'r', encoding='utf-8') as f:
                    ayarlar = json.load(f)
                
                # Son pozisyonu yükle (sadece ilgili kategori için)
                if self.aktif_kategori == kategori:
                    self.aktif_klasor = ayarlar.get('son_klasor')
                    self.aktif_desen_index = ayarlar.get('son_index', 0)
                
                # Panel genişliklerini yükle (ilk yüklenen kategori belirler)
                if 'sol_panel_genislik' in ayarlar:
                    self.sol_panel_genislik = ayarlar['sol_panel_genislik']
                    self.sol_panel.configure(width=self.sol_panel_genislik)
                
                if 'sag_panel_genislik' in ayarlar:
                    self.sag_panel_genislik = ayarlar['sag_panel_genislik']
                    self.sag_panel.configure(width=self.sag_panel_genislik)
                
                # Logo yolunu yükle ve göster (ilk kategori belirler)
                if not self.logo_yolu and ayarlar.get('logo_yolu') and Path(ayarlar['logo_yolu']).exists():
                    self.logo_yolu = ayarlar['logo_yolu']
                    try:
                        self.logo_goster(self.logo_yolu)
                    except Exception:
                        pass
        except Exception as e:
            print(f"{kategori} ayarları yüklenemedi: {str(e)}")
        
    def alt_klasorleri_yukle(self, kategori):
        """Alt klasörleri tara ve desenleri yükle - kategori bazlı - OPTIMIZE EDİLDİ"""
        print(f"{kategori} taranıyor...")
        
        ana_klasor = self.desenler_ana_klasor if kategori == "Desenler" else self.varyantlar_ana_klasor
        etiketler_dosyasi = self.desenler_etiketler_dosyasi if kategori == "Desenler" else self.varyantlar_etiketler_dosyasi
        
        if not ana_klasor or not ana_klasor.exists():
            print(f"⚠️ {kategori} ana klasörü bulunamadı!")
            return
        
        desteklenen_formatlar = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        desenler_dict = {}
        
        # Ana klasör altındaki tüm alt klasörleri tara
        for alt_klasor in ana_klasor.iterdir():
            if alt_klasor.is_dir():
                desenler = []
                for dosya in alt_klasor.iterdir():
                    if dosya.suffix.lower() in desteklenen_formatlar:
                        desen_bilgi = {
                            'dosya': dosya,
                            'ad': dosya.name,
                            'boyut': 0,  # Lazy load - gerekince hesaplanacak
                            'etiketler': []
                        }
                        # Kaydedilmiş etiketleri yükle
                        dosya_key = str(dosya.relative_to(ana_klasor))
                        if hasattr(self, f'{kategori.lower()}_kaydedilmis_etiketler'):
                            kaydedilmis = getattr(self, f'{kategori.lower()}_kaydedilmis_etiketler')
                            if dosya_key in kaydedilmis:
                                desen_bilgi['etiketler'] = kaydedilmis[dosya_key]
                        # Numara ve arama metni ekle
                        desen_bilgi['numara'] = self.desen_numarasini_cikar(dosya.name)
                        desen_bilgi['search_text'] = self.olustur_search_text(dosya.name, desen_bilgi['etiketler'])
                        desenler.append(desen_bilgi)
                
                if desenler:
                    desenler_dict[alt_klasor.name] = sorted(desenler, key=lambda x: x['ad'])
        
        # Kategoriyi güncelle
        if kategori == "Desenler":
            self.desenler = desenler_dict
        else:
            self.varyantlar = desenler_dict
        
        print(f"✅ {len(desenler_dict)} klasör, {sum(len(d) for d in desenler_dict.values())} {kategori.lower()} yüklendi")
    
    def cache_kaydet(self, kategori):
        """Desen listesini cache'e kaydet - kategori bazlı"""
        cache_dosyasi = self.desenler_cache_dosyasi if kategori == "Desenler" else self.varyantlar_cache_dosyasi
        
        if not cache_dosyasi:
            return
        
        try:
            import time
            desenler_dict = self.desenler if kategori == "Desenler" else self.varyantlar
            
            cache_data = {
                'timestamp': time.time(),
                'desenler': {}
            }
            
            # Desenleri kaydet
            for klasor_adi, desenler in desenler_dict.items():
                cache_data['desenler'][klasor_adi] = [
                    {
                        'dosya': str(desen['dosya']),
                        'ad': desen['ad'],
                        'boyut': desen['boyut'],
                        'etiketler': desen.get('etiketler', []),
                        'numara': desen.get('numara', self.desen_numarasini_cikar(desen.get('ad', '')))
                    }
                    for desen in desenler
                ]
            
            with open(cache_dosyasi, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            print(f"{kategori} cache kaydedildi!")
        except Exception as e:
            print(f"{kategori} cache kaydetme hatası: {e}")
                    
    def klasor_listesini_guncelle(self):
        """Klasör listesini aktif kategoriye göre güncelle"""
        # Eski widget'ları temizle
        for widget in self.klasor_listesi.winfo_children():
            widget.destroy()
        
        # Aktif kategorinin desenlerini al
        aktif_desenler = self.get_aktif_kategori_desenler()
        
        if not aktif_desenler:
            # Klasör yoksa mesaj göster
            bos_label = ctk.CTkLabel(
                self.klasor_listesi,
                text=f"'{self.aktif_kategori}' klasöründe\nalt klasör bulunamadı",
                text_color="gray",
                font=ctk.CTkFont(size=12)
            )
            bos_label.grid(row=0, column=0, padx=10, pady=20)
            return
        
        # Özel klasörler (hep en üstte)
        ozel_klasorler = ["yeni tasarımlar", "yeni desen varyantları"]
        
        # Klasörleri sırala: önce özel klasörler, sonra alfabetik
        tum_klasorler = list(aktif_desenler.keys())
        sirali_klasorler = []
        
        # Önce özel klasörleri ekle (varsa) - büyük/küçük harf duyarsız
        for klasor in tum_klasorler:
            klasor_lower = klasor.lower()
            if klasor_lower in [k.lower() for k in ozel_klasorler]:
                sirali_klasorler.append(klasor)
        
        # Sonra diğer klasörleri alfabetik ekle
        diger_klasorler = []
        for klasor in tum_klasorler:
            klasor_lower = klasor.lower()
            if klasor_lower not in [k.lower() for k in ozel_klasorler]:
                diger_klasorler.append(klasor)
        
        # Diğerlerini alfabetik sırala ve ekle
        sirali_klasorler.extend(sorted(diger_klasorler))
            
        # Yeni klasör butonları ekle
        for i, klasor_adi in enumerate(sirali_klasorler):
            desen_sayisi = len(aktif_desenler[klasor_adi])
            
            # Özel klasör mü kontrol et
            ozel_mi = klasor_adi.lower() in [k.lower() for k in ozel_klasorler]
            
            # Seçili mi kontrol et
            secili_mi = (self.aktif_klasor == klasor_adi)
            
            # Renk belirleme - seçili ise yeşil, değilse mavi
            if secili_mi:
                ana_renk = "#2e7d32"  # Koyu yeşil (seçili)
                hover_renk = "#1b5e20"  # Daha koyu yeşil
            else:
                ana_renk = "#1f6aa5"  # Mavi (normal)
                hover_renk = "#144870"  # Koyu mavi
            
            # Klasör adını kısalt (çok uzunsa)
            max_uzunluk = 18 if ozel_mi else 28  # Yıldızlar için daha fazla yer bırak
            klasor_goster = klasor_adi
            if len(klasor_adi) > max_uzunluk:
                klasor_goster = klasor_adi[:max_uzunluk-3] + "..."
            
            # Tıklanabilir frame (buton gibi)
            frame = ctk.CTkFrame(
                self.klasor_listesi,
                fg_color=ana_renk,
                corner_radius=6,
                height=50 if ozel_mi else 40,  # Özel klasör için daha yüksek
                cursor="hand2"
            )
            frame.grid(row=i, column=0, padx=5, pady=3, sticky="ew")
            frame.grid_propagate(False)
            
            if ozel_mi:
                # Özel klasör için grid ayarları
                frame.grid_columnconfigure(0, weight=0)  # Sol yıldızlar
                frame.grid_columnconfigure(1, weight=1)  # Klasör adı ve sayı
                frame.grid_columnconfigure(2, weight=0)  # Sağ yıldızlar
                frame.grid_rowconfigure(0, weight=1)
                
                # Sol yıldızlar (sarı)
                sol_yildiz = ctk.CTkLabel(
                    frame,
                    text="★★★",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color="#FFD700"  # Parlak altın sarısı
                )
                sol_yildiz.grid(row=0, column=0, sticky="w", padx=(8, 5))
                
                # Orta kısım - Klasör adı ve sayısı birlikte
                orta_text = f"{klasor_goster}\n({desen_sayisi} desen)"
                orta_label = ctk.CTkLabel(
                    frame,
                    text=orta_text,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="white",
                    justify="center"
                )
                orta_label.grid(row=0, column=1, sticky="ew", padx=5)
                
                # Sağ yıldızlar (sarı)
                sag_yildiz = ctk.CTkLabel(
                    frame,
                    text="★★★",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color="#FFD700"  # Parlak altın sarısı
                )
                sag_yildiz.grid(row=0, column=2, sticky="e", padx=(5, 8))
            else:
                # Normal klasör için grid ayarları
                frame.grid_columnconfigure(0, weight=1)
                frame.grid_rowconfigure(0, weight=1)
                frame.grid_rowconfigure(1, weight=1)
                
                # Klasör adı label (beyaz)
                klasor_label = ctk.CTkLabel(
                    frame,
                    text=klasor_goster,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="white"
                )
                klasor_label.grid(row=0, column=0, sticky="ew", padx=5)
                
                # Desen sayısı label (kırmızı)
                sayi_label = ctk.CTkLabel(
                    frame,
                    text=f"({desen_sayisi} desen)",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#ff5252"
                )
                sayi_label.grid(row=1, column=0, sticky="ew", padx=5)
            
            # Hover efekti için bind
            def on_enter(e, f=frame, hr=hover_renk):
                f.configure(fg_color=hr)
            def on_leave(e, f=frame, ar=ana_renk):
                f.configure(fg_color=ar)
            def on_click(e, k=klasor_adi):
                self.klasor_sec_desen(k)
            
            # Tüm widget'lara bind - özel klasör için tüm widget'ları topla
            if ozel_mi:
                widgets_to_bind = [frame, sol_yildiz, orta_label, sag_yildiz]
            else:
                widgets_to_bind = [frame, klasor_label, sayi_label]
            
            for widget in widgets_to_bind:
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)
                widget.bind("<Button-1>", on_click)
            
    def kategori_sec(self, kategori):
        """Kategori seç (Desenler veya Varyantlar) ve klasör listesini güncelle"""
        self.aktif_kategori = kategori
        
        # Buton renklerini güncelle
        if kategori == "Desenler":
            self.desenler_btn.configure(fg_color="#ff9800")
            self.varyantlar_btn.configure(fg_color="#424242")
        else:
            self.desenler_btn.configure(fg_color="#424242")
            self.varyantlar_btn.configure(fg_color="#4caf50")
        
        # Durum label'ını güncelle
        self.durum_label_guncelle()
        
        # Observer'ı yeniden başlat (yeni kategorinin klasörünü izle)
        self.observer_baslat()
        
        # Klasör listesini güncelle
        self.klasor_listesini_guncelle()
        
        # İlk klasörü seç (varsa) - özel klasörler önce
        aktif_desenler = self.get_aktif_kategori_desenler()
        if aktif_desenler:
            ozel_klasorler = ["yeni tasarımlar", "yeni desen varyantları"]
            ilk_klasor = None
            
            # Önce özel klasörleri kontrol et - büyük/küçük harf duyarsız
            for klasor in aktif_desenler.keys():
                klasor_lower = klasor.lower()
                if klasor_lower in [k.lower() for k in ozel_klasorler]:
                    ilk_klasor = klasor
                    break
            
            # Özel klasör yoksa alfabetik ilk klasörü al
            if ilk_klasor is None:
                ilk_klasor = sorted(aktif_desenler.keys())[0]
            
            self.klasor_sec_desen(ilk_klasor)
    
    def get_aktif_kategori_desenler(self):
        """Aktif kategorinin desen sözlüğünü döndür"""
        if self.aktif_kategori == "Desenler":
            return self.desenler
        else:
            return self.varyantlar
    
    def klasor_sec_desen(self, klasor_adi):
        """Klasör seç ve ilk deseni göster"""
        self.aktif_klasor = klasor_adi
        self.aktif_desen_index = 0
        self.deseni_goster()
        self.klasor_listesini_guncelle()  # Listeyi güncelle (seçili rengi göster)
        self.ayarlari_kaydet()  # Pozisyonu kaydet
        
    def deseni_goster(self):
        """Aktif deseni göster - fit-to-view ve zoom ile + Preloading"""
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        if not desenler or self.aktif_desen_index >= len(desenler):
            return
            
        desen = desenler[self.aktif_desen_index]
        dosya_yolu = str(desen['dosya'])
        
        # Şu anki resmin yolunu kaydet (zoom ve yeniden çizim için)
        self.current_image_path = dosya_yolu
        
        try:
            # Boş durum mesajını gizle
            self.bos_durum_label.grid_remove()
            
            # Yükleme animasyonu göster
            self._show_loading()
            
            # Başlık güncelle - daha renkli
            self.desen_baslik.configure(
                text=f"🎨 {self.aktif_klasor} • {desen['ad']}",
                text_color="#4fc3f7"
            )
            
            # Dosya bilgisi güncelle - Lazy load boyut
            if desen['boyut'] == 0:
                desen['boyut'] = desen['dosya'].stat().st_size
            boyut_mb = desen['boyut'] / (1024 * 1024)
            try:
                with Image.open(desen['dosya']) as _tmp_img:
                    self._current_original_size = _tmp_img.size
            except Exception:
                self._current_original_size = None
            
            # Görseli mevcut önizleme alanına göre çiz
            self._update_preview_image()
            
            # Yükleme animasyonunu gizle
            self._hide_loading()
            
            # Bilgi güncelle - modern ikonlarla
            if self._current_original_size:
                self.dosya_bilgi.configure(
                    text=f"💾 {boyut_mb:.2f} MB  •  📐 {self._current_original_size[0]}x{self._current_original_size[1]}  •  🔍 {int(self.zoom_level * 100)}%"
                )
            else:
                self.dosya_bilgi.configure(
                    text=f"💾 {boyut_mb:.2f} MB  •  🔍 {int(self.zoom_level * 100)}%"
                )
            
            # Scroll binding'i sadece ilk sefer ekle
            if not hasattr(self, '_scroll_bound'):
                self.desen_label.bind("<MouseWheel>", self._onizleme_scroll_stop)
                self.desen_label.bind("<Button-4>", self._onizleme_scroll_stop)
                self.desen_label.bind("<Button-5>", self._onizleme_scroll_stop)
                self._scroll_bound = True
            
            # Pozisyon güncelle
            self.pozisyon_label.configure(
                text=f"📄 {self.aktif_desen_index + 1} / {len(desenler)}"
            )
            
            # Etiketleri göster
            self.etiketleri_goster()
            
            # Pozisyonu kaydet (throttle ile - her 2 saniyede bir)
            if not hasattr(self, '_save_after_id') or self._save_after_id is None:
                self._save_after_id = self.after(2000, self._kaydet_throttled)
            
            # Sıradaki desenleri arkaplanda yükle (preload)
            self._preload_adjacent_images()
            
        except Exception as e:
            self._hide_loading()
            messagebox.showerror("Hata", f"Desen yüklenemedi: {str(e)}")
    
    def _show_loading(self):
        """Yükleme göstergesini göster"""
        if not self._loading_animation:
            self._loading_animation = True
            self.loading_label.grid(row=0, column=0)
            self._animate_loading()
    
    def _hide_loading(self):
        """Yükleme göstergesini gizle"""
        self._loading_animation = False
        self.loading_label.grid_remove()
    
    def _animate_loading(self):
        """Yükleme animasyonu (dönen nokta efekti)"""
        if not self._loading_animation:
            return
        current_text = self.loading_label.cget("text")
        if "⏳" in current_text:
            self.loading_label.configure(text="⌛ Yükleniyor...")
        else:
            self.loading_label.configure(text="⏳ Yükleniyor...")
        self.after(300, self._animate_loading)
    
    def _preload_adjacent_images(self):
        """Sıradaki ve önceki desenleri arkaplanda yükle (preload için)"""
        try:
            aktif_desenler = self.get_aktif_kategori_desenler()
            if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
                return
            desenler = aktif_desenler[self.aktif_klasor]
            
            # Sonraki deseni yükle
            if self.aktif_desen_index + 1 < len(desenler):
                sonraki_yol = str(desenler[self.aktif_desen_index + 1]['dosya'])
                if sonraki_yol not in self._preload_cache:
                    threading.Thread(
                        target=self._preload_image,
                        args=(sonraki_yol,),
                        daemon=True
                    ).start()
            
            # Önceki deseni yükle
            if self.aktif_desen_index > 0:
                onceki_yol = str(desenler[self.aktif_desen_index - 1]['dosya'])
                if onceki_yol not in self._preload_cache:
                    threading.Thread(
                        target=self._preload_image,
                        args=(onceki_yol,),
                        daemon=True
                    ).start()
        except Exception as e:
            print(f"Preload hatası: {e}")
    
    def _preload_image(self, dosya_yolu):
        """Bir deseni arkaplanda yükle"""
        try:
            if dosya_yolu not in self._preload_cache:
                img = Image.open(dosya_yolu)
                # Sadece metadata'yı cache'le, tam yüklemeyi gösterim anında yap
                self._preload_cache[dosya_yolu] = img.size
                print(f"✅ Preload: {Path(dosya_yolu).name}")
        except Exception as e:
            print(f"Preload hatası: {dosya_yolu} - {e}")
    
    def _kaydet_throttled(self):
        """Throttled kaydetme - çok sık kaydetmeyi önler"""
        self.ayarlari_kaydet()
        self._save_after_id = None
            
    def onceki_desen(self):
        """Önceki desene geç + Smooth transition"""
        # Zoom'u sıfırla
        self.zoom_level = 1.0
        
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        if self.aktif_desen_index > 0:
            self.aktif_desen_index -= 1
            # Küçük bir gecikme ile smooth geçiş hissi
            self.after(50, self.deseni_goster)
    
    def _onizleme_scroll_stop(self, event):
        """Mouse scroll wheel ile ana menüde desen değiştir - event propagation'u durdur"""
        try:
            # Event tipine göre yön belirle
            if event.type == "38":  # MouseWheel event
                if event.delta > 0:  # Scroll up - önceki
                    self.onceki_desen()
                else:  # Scroll down - sonraki
                    self.sonraki_desen()
            elif event.num == 4:  # Linux Button-4 (scroll up)
                self.onceki_desen()
            elif event.num == 5:  # Linux Button-5 (scroll down)
                self.sonraki_desen()
            return "break"  # Event propagation'u durdur
        except Exception as e:
            print(f"Scroll hatası: {e}")
            return "break"
    
    def _onizleme_zoom(self, event):
        """Ctrl + Mouse scroll ile zoom yap"""
        try:
            if not self.current_image_path:
                return "break"
            
            # Zoom yönünü belirle
            if event.type == "38":  # MouseWheel event
                if event.delta > 0:  # Scroll up - zoom in
                    self.zoom_level = min(self.max_zoom, self.zoom_level + self.zoom_step)
                else:  # Scroll down - zoom out
                    self.zoom_level = max(self.min_zoom, self.zoom_level - self.zoom_step)
            elif event.num == 4:  # Linux Button-4 (scroll up)
                self.zoom_level = min(self.max_zoom, self.zoom_level + self.zoom_step)
            elif event.num == 5:  # Linux Button-5 (scroll down)
                self.zoom_level = max(self.min_zoom, self.zoom_level - self.zoom_step)
            
            # Resmi yeniden boyutlandır
            self._apply_zoom()
            return "break"
        except Exception as e:
            print(f"Zoom hatası: {e}")
            return "break"

    def _on_preview_area_resize(self, event):
        """Önizleme alanı değiştiğinde görseli alana göre tekrar çiz (debounce)."""
        try:
            if not self.current_image_path:
                return
            if self._preview_resize_job is not None:
                try:
                    self.after_cancel(self._preview_resize_job)
                except Exception:
                    pass
            self._preview_resize_job = self.after(120, self._update_preview_image)
        except Exception as e:
            print(f"Önizleme alanı resize hatası: {e}")

    def _update_preview_image(self):
        """Mevcut resmi, önizleme alanına sığacak şekilde (oran koruyarak) çiz + akıllı yükleme."""
        try:
            self._preview_resize_job = None
            if not self.current_image_path:
                return
            
            # Önizleme alanı boyutu (label padding: 20px x 20px)
            alan_w = max(1, self.onizleme_frame.winfo_width() - 40)
            alan_h = max(1, self.onizleme_frame.winfo_height() - 40)
            if alan_w <= 1 or alan_h <= 1:
                # UI henüz hazır değilse makul değerler
                alan_w, alan_h = 600, 500
            
            # Preload cache kontrolü
            if self.current_image_path in self._preload_cache:
                ow, oh = self._preload_cache[self.current_image_path]
            else:
                # İlk yükleme - hızlı metadata okuma
                with Image.open(self.current_image_path) as img:
                    ow, oh = img.size
                    self._preload_cache[self.current_image_path] = (ow, oh)
            
            # Ölçek: ALANA SIĞDIR (contain) + zoom
            scale = min(alan_w / ow, alan_h / oh)
            scale = max(0.01, scale) * float(self.zoom_level)
            nw = max(1, int(ow * scale))
            nh = max(1, int(oh * scale))
            
            # Çok büyük upscale'i önle (kalite kaybı)
            max_upscale = 2.0
            actual_scale = min(nw / ow, nh / oh)
            if actual_scale > max_upscale:
                nw = int(ow * max_upscale)
                nh = int(oh * max_upscale)
            
            # Gerçek resmi yükle ve boyutlandır
            with Image.open(self.current_image_path) as img:
                img_resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
            
            ctk_img = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=(nw, nh))
            self.desen_label.configure(image=ctk_img, text="")
            self.desen_label.image = ctk_img
            
            # Fade-in efekti simülasyonu (alpha değişimi)
            self._fade_in_effect()
            
        except Exception as e:
            print(f"Önizleme güncelleme hatası: {e}")
    
    def _fade_in_effect(self):
        """Görsel yüklendiğinde hafif fade-in efekti"""
        if self._fade_in_progress:
            return
        self._fade_in_progress = True
        # CustomTkinter alpha desteği sınırlı, ama grid/pack animasyonu yapabiliriz
        # Basit görünürlük efekti
        self.after(50, lambda: setattr(self, '_fade_in_progress', False))
    
    def _apply_zoom(self):
        """Zoom seviyesini uygula (fit-to-view tabanlı) + Bilgi güncellemesi."""
        try:
            if not self.current_image_path:
                return
            # Görseli mevcut önizleme alanına göre yeniden çiz
            self._update_preview_image()
            
            # Zoom bilgisini dosya bilgisine ekle - Modern ikonlarla
            aktif_desenler = self.get_aktif_kategori_desenler()
            if self.aktif_klasor and self.aktif_klasor in aktif_desenler:
                desenler = aktif_desenler[self.aktif_klasor]
                if self.aktif_desen_index < len(desenler):
                    desen = desenler[self.aktif_desen_index]
                    boyut_mb = desen['boyut'] / (1024 * 1024)
                    zoom_percent = int(self.zoom_level * 100)
                    # Orijinal çözünürlüğü göster (mevcutsa)
                    if hasattr(self, '_current_original_size') and self._current_original_size:
                        ow, oh = self._current_original_size
                        self.dosya_bilgi.configure(
                            text=f"💾 {boyut_mb:.2f} MB  •  📐 {ow}x{oh}  •  🔍 {zoom_percent}%"
                        )
                    else:
                        self.dosya_bilgi.configure(
                            text=f"💾 {boyut_mb:.2f} MB  •  🔍 {zoom_percent}%"
                        )
        except Exception as e:
            print(f"Zoom uygulama hatası: {e}")
    
    def _zoom_sifirla(self):
        """Zoom'u normal boyuta döndür (sağ tık)"""
        self.zoom_level = 1.0
        if self.current_image_path:
            self._apply_zoom()
            
    def sonraki_desen(self):
        """Sonraki desene geç + Smooth transition"""
        # Zoom'u sıfırla
        self.zoom_level = 1.0
        
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        if self.aktif_desen_index < len(desenler) - 1:
            self.aktif_desen_index += 1
            # Küçük bir gecikme ile smooth geçiş hissi
            self.after(50, self.deseni_goster)
            
    def etiket_ekle(self):
        """Aktif desene etiket ekle"""
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            messagebox.showwarning("Uyarı", "Lütfen önce bir desen seçin")
            return
            
        etiket = self.etiket_entry.get().strip()
        if not etiket:
            messagebox.showwarning("Uyarı", "Lütfen bir etiket girin")
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        desen = desenler[self.aktif_desen_index]
        
        if etiket not in desen['etiketler']:
            desen['etiketler'].append(etiket)
            # Arama metnini güncelle (hızlı arama için)
            desen['search_text'] = self.olustur_search_text(desen['ad'], desen['etiketler'])
            self.etiket_entry.delete(0, 'end')
            self.etiketleri_goster()
            self.etiketleri_kaydet()
            self.istatistikleri_guncelle()
            
            
    def etiketleri_goster(self):
        """Aktif desenin etiketlerini göster - Modern kartlar"""
        # Eski widget'ları temizle
        for widget in self.etiketler_listesi.winfo_children():
            widget.destroy()

        # Tüm etiketler combobox'ını güncelle (güzelleştirilmiş görünümle)
        try:
            _tum_etik_orj = self.get_tum_etiketler()
            _tum_etik_pretty = [self.format_etiket_gorunumu(e) for e in _tum_etik_orj]
            self._tum_etiket_map = {p: o for p, o in zip(_tum_etik_pretty, _tum_etik_orj)}
            self.tum_etiketler_combo.configure(values=_tum_etik_pretty)
            # Değer güncellenince bazı sürümlerde ilk öğe seçilebiliyor; yine boş bırak
            self.tum_etiketler_combo.set("")
        except Exception:
            pass
            
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        desen = desenler[self.aktif_desen_index]
        
        if not desen['etiketler']:
            # Boş durum mesajı - modern
            bos_frame = ctk.CTkFrame(
                self.etiketler_listesi,
                corner_radius=8,
                fg_color="transparent"
            )
            bos_frame.grid(row=0, column=0, padx=5, pady=10, sticky="ew")
            
            label = ctk.CTkLabel(
                bos_frame,
                text="📝 Henüz etiket eklenmemiş\n\n💡 Yukarıdan etiket ekleyebilirsiniz",
                font=ctk.CTkFont(size=12),
                text_color="gray",
                justify="center"
            )
            label.pack(pady=15)
            return
            
        for i, etiket in enumerate(desen['etiketler']):
            # Modern etiket kartı
            frame = ctk.CTkFrame(
                self.etiketler_listesi, 
                corner_radius=8,
                border_width=2,
                border_color="#4fc3f7",
                fg_color="#1e1e1e"
            )
            frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            frame.grid_columnconfigure(0, weight=1)
            
            # Hover efekti için
            def on_enter(e, f=frame):
                f.configure(fg_color="#2a2a2a", border_color="#64b5f6")
            def on_leave(e, f=frame):
                f.configure(fg_color="#1e1e1e", border_color="#4fc3f7")
            
            frame.bind("<Enter>", on_enter)
            frame.bind("<Leave>", on_leave)
            
            label = ctk.CTkLabel(
                frame,
                text=f"🔖 {etiket}",
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
                text_color="#4fc3f7"
            )
            label.grid(row=0, column=0, padx=12, pady=10, sticky="w")
            label.bind("<Enter>", on_enter)
            label.bind("<Leave>", on_leave)
            
            sil_btn = ctk.CTkButton(
                frame,
                text="🗑️",
                command=lambda e=etiket: self.etiket_sil(e),
                fg_color="#f44336",
                hover_color="#ef5350",
                width=35,
                height=30,
                corner_radius=6,
                font=ctk.CTkFont(size=14)
            )
            sil_btn.grid(row=0, column=1, padx=8, pady=8)
            
    def etiket_sil(self, etiket):
        """Etiketi sil"""
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
            return
            
        desenler = aktif_desenler[self.aktif_klasor]
        desen = desenler[self.aktif_desen_index]
        
        if etiket in desen['etiketler']:
            desen['etiketler'].remove(etiket)
            # Arama metnini güncelle (hızlı arama için)
            desen['search_text'] = self.olustur_search_text(desen['ad'], desen['etiketler'])
            self.etiketleri_goster()
            self.etiketleri_kaydet()
            self.istatistikleri_guncelle()

    
            
    def etiketleri_kaydet(self):
        """Etiketleri JSON dosyasına kaydet - kategori bazlı"""
        # Desenler etiketlerini kaydet
        if self.desenler_etiketler_dosyasi and self.desenler_ana_klasor:
            etiket_verisi = {}
            for klasor_adi, desenler in self.desenler.items():
                for desen in desenler:
                    dosya_key = str(desen['dosya'].relative_to(self.desenler_ana_klasor))
                    if desen['etiketler']:
                        etiket_verisi[dosya_key] = desen['etiketler']
            
            try:
                with open(self.desenler_etiketler_dosyasi, 'w', encoding='utf-8') as f:
                    json.dump(etiket_verisi, f, ensure_ascii=False, indent=2)
            except Exception as e:
                messagebox.showerror("Hata", f"Desenler etiketleri kaydedilemedi: {str(e)}")
        
        # Varyantlar etiketlerini kaydet
        if self.varyantlar_etiketler_dosyasi and self.varyantlar_ana_klasor:
            etiket_verisi = {}
            for klasor_adi, desenler in self.varyantlar.items():
                for desen in desenler:
                    dosya_key = str(desen['dosya'].relative_to(self.varyantlar_ana_klasor))
                    if desen['etiketler']:
                        etiket_verisi[dosya_key] = desen['etiketler']
            
            try:
                with open(self.varyantlar_etiketler_dosyasi, 'w', encoding='utf-8') as f:
                    json.dump(etiket_verisi, f, ensure_ascii=False, indent=2)
            except Exception as e:
                messagebox.showerror("Hata", f"Varyantlar etiketleri kaydedilemedi: {str(e)}")
            
    def etiketleri_yukle(self, kategori):
        """Kaydedilmiş etiketleri yükle - kategori bazlı"""
        etiketler_dosyasi = self.desenler_etiketler_dosyasi if kategori == "Desenler" else self.varyantlar_etiketler_dosyasi
        attr_name = f'{kategori.lower()}_kaydedilmis_etiketler'
        
        if not etiketler_dosyasi or not etiketler_dosyasi.exists():
            setattr(self, attr_name, {})
            return
            
        try:
            with open(etiketler_dosyasi, 'r', encoding='utf-8') as f:
                setattr(self, attr_name, json.load(f))
        except Exception as e:
            setattr(self, attr_name, {})
            messagebox.showwarning("Uyarı", f"{kategori} etiketleri yüklenemedi: {str(e)}")
    
    def arama_debounce(self, event=None):
        """Arama için debounce - 300ms sonra ara"""
        # Önceki arama işlemini iptal et
        if self._arama_after_id:
            self.after_cancel(self._arama_after_id)
        
        # Yeni arama işlemini planla (300ms sonra)
        self._arama_after_id = self.after(300, self.arama_yap)
            
    def arama_yap(self, event=None):
        """Desen/numara/etiket arama - hızlı ve doğru sonuç"""
        import os
        arama_terimi = self.arama_entry.get().strip().lower()
        if not arama_terimi:
            self.klasor_listesini_guncelle()
            self.arama_sonuclari = []
            self.secili_desenler = set()
            return
            
        # Eski widget'ları temizle
        for widget in self.klasor_listesi.winfo_children():
            widget.destroy()
            
        bulunan_sayac = 0
        self.arama_sonuclari = []
        
        tokens = [t for t in arama_terimi.split() if t]

        # Desenler kategorisinde ara
        for klasor_adi, desenler in self.desenler.items():
            for idx, desen in enumerate(desenler):
                st = desen.get('search_text') or self.olustur_search_text(desen['ad'], desen.get('etiketler', []))
                if all(t in st for t in tokens):
                    self.arama_sonuclari.append(("Desenler", klasor_adi, idx))
        
        # Varyantlar kategorisinde ara
        for klasor_adi, desenler in self.varyantlar.items():
            for idx, desen in enumerate(desenler):
                st = desen.get('search_text') or self.olustur_search_text(desen['ad'], desen.get('etiketler', []))
                if all(t in st for t in tokens):
                    self.arama_sonuclari.append(("Varyantlar", klasor_adi, idx))
                        
        if self.arama_sonuclari:
            # Her bulunan desen için seçim checkbox'lı buton
            for i, (kategori, klasor_adi, desen_idx) in enumerate(self.arama_sonuclari):
                # Kategoriye göre doğru dict'i seç
                desenler_dict = self.desenler if kategori == "Desenler" else self.varyantlar
                desen = desenler_dict[klasor_adi][desen_idx]
                
                # Frame oluştur
                item_frame = ctk.CTkFrame(self.klasor_listesi, corner_radius=6)
                item_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
                item_frame.grid_columnconfigure(1, weight=1)
                
                # Checkbox
                secili = (kategori, klasor_adi, desen_idx) in self.secili_desenler
                checkbox_var = ctk.BooleanVar(value=secili)
                checkbox = ctk.CTkCheckBox(
                    item_frame,
                    text="",
                    variable=checkbox_var,
                    width=30,
                    command=lambda kat=kategori, k=klasor_adi, d=desen_idx, v=checkbox_var: self.desen_secim_degistir(kat, k, d, v)
                )
                checkbox.grid(row=0, column=0, padx=(10, 5), pady=10)
                
                # Desen bilgisi butonu
                kategori_emoji = "🎨" if kategori == "Desenler" else "🔄"
                klasor_goster = klasor_adi
                if len(klasor_adi) > 18:
                    klasor_goster = klasor_adi[:15] + "..."
                
                isim_stem = os.path.splitext(desen['ad'])[0]
                dosya_goster = isim_stem if len(isim_stem) <= 20 else isim_stem[:17] + "..."
                no_goster = desen.get('numara')
                no_satir = f"\n# {no_goster}" if no_goster else ""
                
                etiket_str = ""
                if desen['etiketler']:
                    etiket_kisaltilmis = []
                    for etiket in desen['etiketler'][:2]:
                        if len(etiket) > 12:
                            etiket_kisaltilmis.append(etiket[:9] + "...")
                        else:
                            etiket_kisaltilmis.append(etiket)
                    etiket_str = f"\n🏷️ {', '.join(etiket_kisaltilmis)}"
                    if len(desen['etiketler']) > 2:
                        etiket_str += "..."
                
                btn = ctk.CTkButton(
                    item_frame,
                    text=f"{kategori_emoji} {klasor_goster}\n{dosya_goster}{no_satir}{etiket_str}",
                    command=lambda kat=kategori, k=klasor_adi, d=desen_idx: self.desene_git(kat, k, d),
                    fg_color="#1f6aa5",
                    hover_color="#144870",
                    height=70,
                    anchor="center",
                    font=ctk.CTkFont(size=11)
                )
                btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
                
                bulunan_sayac += 1
            
            # PDF oluştur butonu (arama sonuçları için)
            if self.secili_desenler:
                pdf_frame = ctk.CTkFrame(self.klasor_listesi, corner_radius=6, fg_color="#1f6aa5")
                pdf_frame.grid(row=bulunan_sayac, column=0, padx=5, pady=10, sticky="ew")
                pdf_btn = ctk.CTkButton(
                    pdf_frame,
                    text=f"📄 Seçili Desenlerden\nPDF Oluştur ({len(self.secili_desenler)})",
                    command=self.secili_desenlerden_pdf_secenekleri_goster,
                    fg_color="#1f6aa5",
                    hover_color="#144870",
                    height=50,
                    font=ctk.CTkFont(size=13, weight="bold")
                )
                pdf_btn.pack(padx=5, pady=5, fill="x")
        else:
            # Sonuç bulunamadıysa bilgi göster
            label = ctk.CTkLabel(
                self.klasor_listesi,
                text=f"'{arama_terimi}' için\nsonuç bulunamadı",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            label.grid(row=0, column=0, padx=10, pady=20)
    
    def desene_git(self, kategori, klasor_adi, desen_index):
        """Belirli bir desene git - kategori değiştirme ile"""
        # Önce kategoriyi değiştir (gerekirse)
        if self.aktif_kategori != kategori:
            self.aktif_kategori = kategori
            # Kategori butonlarını güncelle
            if kategori == "Desenler":
                self.desenler_btn.configure(fg_color="#ff9800")
                self.varyantlar_btn.configure(fg_color="#424242")
            else:
                self.desenler_btn.configure(fg_color="#424242")
                self.varyantlar_btn.configure(fg_color="#4caf50")
            
            # Observer'ı yeniden başlat (yeni kategorinin klasörünü izle)
            self.observer_baslat()
        
        # Klasör ve deseni seç
        self.aktif_klasor = klasor_adi
        self.aktif_desen_index = desen_index
        
        # Deseni göster
        self.deseni_goster()
        
        # Durum label'ını güncelle
        self.durum_label_guncelle()
        
        # Ayarları kaydet
        self.ayarlari_kaydet()
        
        # Arama kutusunu temizle (arama sonuçlarından geldiğimiz için)
        if self.arama_entry.get():
            self.arama_entry.delete(0, 'end')
            # Klasör listesini normal haline getir
            self.klasor_listesini_guncelle()
    
    def secili_desenlerden_pdf_olustur(self):
        """Seçili desenlerden PDF oluştur (her desen tek A4, Türkçe filigran)"""
        if not self.secili_desenler:
            messagebox.showwarning("Uyarı", "Lütfen PDF'e eklemek için desenler seçin")
            return
        dosya_yolu = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF dosyaları", "*.pdf")],
            title="PDF Kaydet"
        )
        if not dosya_yolu:
            return
        try:
            # ReportLab lazy import - sadece burda yükle
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import reportlab.rl_config
            reportlab.rl_config.warnOnMissingFontGlyphs = 0
            
            # DejaVuSans fontunu ekle (Türkçe karakter desteği için)
            font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
            if not os.path.exists(font_path):
                messagebox.showwarning("Uyarı", "DejaVuSans.ttf dosyası uygulama klasöründe yok. Türkçe karakterler için bu font gereklidir!")
            else:
                pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            c = canvas.Canvas(dosya_yolu, pagesize=A4)
            width, height = A4
            filigran_ekle = self.filigran_var.get()
            secili_list = sorted(self.secili_desenler)
            
            # Desen objelerini kategori ile birlikte al
            desen_objs = []
            for kategori, klasor, idx in secili_list:
                desenler_dict = self.desenler if kategori == "Desenler" else self.varyantlar
                desen_objs.append(desenler_dict[klasor][idx])
            
            for desen in desen_objs:
                # Resmi büyük şekilde ortala
                try:
                    img = Image.open(desen['dosya'])
                    max_width = width - 100
                    max_height = height - 180
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    img_io = io.BytesIO()
                    img.save(img_io, format='PNG')
                    img_io.seek(0)
                    x = (width - img.width) / 2
                    y = (height - img.height) / 2 + 30
                    c.drawImage(ImageReader(img_io), x, y, width=img.width, height=img.height)
                    
                    # Altına isim
                    c.setFont("DejaVuSans" if os.path.exists(font_path) else "Helvetica", 14)
                    c.drawCentredString(width/2, y-20, desen['ad'])
                except Exception as e:
                    print(f"Desen eklenemedi: {desen['ad']} - {str(e)}")
                    continue
                # Filigran ekle
                if filigran_ekle:
                    c.saveState()
                    c.setFont("DejaVuSans" if os.path.exists(font_path) else "Helvetica-Bold", 36)
                    c.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.22)
                    c.translate(width/2, height/2)
                    c.rotate(45)
                    text = "ORHAN KARAKOÇ TEKSTİL"
                    c.drawCentredString(0, 0, text)
                    c.restoreState()
                c.showPage()
            c.save()
            messagebox.showinfo(
                "Başarılı",
                f"Seçili desenlerden PDF oluşturuldu!\n{len(secili_list)} desen\n{len(secili_list)} sayfa\n{dosya_yolu}"
            )
            self.secili_desenler = set()
            self.arama_yap()
        except Exception as e:
            messagebox.showerror("Hata", f"PDF oluşturulamadı: {str(e)}")
    
    def filigran_ekle_pdf(self, c, width, height):
        """PDF'e filigran ekle"""
        c.saveState()
        c.setFont("Helvetica-Bold", 60)
        c.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.3)
        
        # Çapraz filigran
        c.translate(width / 2, height / 2)
        c.rotate(45)
        
        # Metni ortala
        text = "ORHAN KARAKOÇ TEKSTİL"
        text_width = c.stringWidth(text, "Helvetica-Bold", 60)
        c.drawString(-text_width / 2, 0, text)
        
        c.restoreState()
            
    def cikis_yap(self):
        """Uygulamadan çık"""
        if messagebox.askyesno("Çıkış", "Uygulamadan çıkmak istediğinize emin misiniz?"):
            self.quit()
    
    def get_aktif_kategori_desenler(self):
        """Aktif kategorideki tüm desenleri döndür"""
        return self.desenler if self.aktif_kategori == "Desenler" else self.varyantlar
    
    def pdf_olustur(self):
        """Aktif kategorideki tüm desenlerden PDF oluştur"""
        aktif_desenler = self.get_aktif_kategori_desenler()
        if not aktif_desenler:
            messagebox.showwarning("Uyarı", "PDF oluşturmak için desenler yükleyin")
            return
        
        dosya_yolu = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF dosyaları", "*.pdf")],
            title="PDF Kaydet"
        )
        if not dosya_yolu:
            return
        
        try:
            # ReportLab lazy import
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import reportlab.rl_config
            reportlab.rl_config.warnOnMissingFontGlyphs = 0
            
            # Font yükle
            font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
            if not os.path.exists(font_path):
                messagebox.showwarning("Uyarı", "DejaVuSans.ttf dosyası uygulama klasöründe yok. Türkçe karakterler için bu font gereklidir!")
            else:
                pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            
            c = canvas.Canvas(dosya_yolu, pagesize=A4)
            width, height = A4
            filigran_ekle = self.filigran_var.get()
            
            # Tüm desenleri topla
            desen_sayisi = 0
            for klasor_adi in sorted(aktif_desenler.keys()):
                for desen in aktif_desenler[klasor_adi]:
                    desen_sayisi += 1
                    try:
                        # Resmi ekle
                        img = Image.open(desen['dosya'])
                        max_width = width - 100
                        max_height = height - 180
                        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                        img_io = io.BytesIO()
                        img.save(img_io, format='PNG')
                        img_io.seek(0)
                        x = (width - img.width) / 2
                        y = (height - img.height) / 2 + 30
                        c.drawImage(ImageReader(img_io), x, y, width=img.width, height=img.height)
                        
                        # Desen adı
                        c.setFont("DejaVuSans" if os.path.exists(font_path) else "Helvetica", 14)
                        c.drawCentredString(width/2, y-20, desen['ad'])
                        
                        # Filigran
                        if filigran_ekle:
                            c.saveState()
                            c.setFont("DejaVuSans" if os.path.exists(font_path) else "Helvetica-Bold", 36)
                            c.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.22)
                            c.translate(width/2, height/2)
                            c.rotate(45)
                            c.drawCentredString(0, 0, "ORHAN KARAKOÇ TEKSTİL")
                            c.restoreState()
                        
                        c.showPage()
                    except Exception as e:
                        print(f"Desen eklenemedi: {desen['ad']} - {str(e)}")
                        continue
            
            c.save()
            messagebox.showinfo(
                "Başarılı",
                f"PDF oluşturuldu!\n{desen_sayisi} desen\n{desen_sayisi} sayfa\n{dosya_yolu}"
            )
        except Exception as e:
            messagebox.showerror("Hata", f"PDF oluşturulamadı: {str(e)}")
    
    def pdf_secenekleri_goster(self):
        """PDF oluşturma seçeneklerini göster"""
        if not self.desenler:
            messagebox.showwarning("Uyarı", "PDF oluşturmak için desenler yükleyin")
            return
        
        secenekler_pencere = ctk.CTkToplevel(self)
        secenekler_pencere.title("PDF Seçenekleri")
        secenekler_pencere.geometry("400x250")
        secenekler_pencere.resizable(False, False)
        secenekler_pencere.transient(self)
        secenekler_pencere.grab_set()
        
        # Ana pencereyi ortasında konumlandır
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 125
        secenekler_pencere.geometry(f"400x250+{x}+{y}")
        
        baslik = ctk.CTkLabel(
            secenekler_pencere,
            text="📄 PDF Oluşturma Seçenekleri",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        baslik.pack(pady=20)
        
        filigran_frame = ctk.CTkFrame(secenekler_pencere)
        filigran_frame.pack(pady=20, padx=30, fill="x")
        
        filigran_label = ctk.CTkLabel(
            filigran_frame,
            text="Filigran Ekle:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        filigran_label.pack(side="left", padx=10)
        
        filigran_switch = ctk.CTkSwitch(
            filigran_frame,
            text="ORHAN KARAKOÇ TEKSTİL",
            variable=self.filigran_var,
            font=ctk.CTkFont(size=12)
        )
        filigran_switch.pack(side="left", padx=10)
        
        aciklama = ctk.CTkLabel(
            secenekler_pencere,
            text="Filigran açıksa her sayfaya\n'ORHAN KARAKOÇ TEKSTİL' yazısı eklenir",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        aciklama.pack(pady=10)
        
        buton_frame = ctk.CTkFrame(secenekler_pencere, fg_color="transparent")
        buton_frame.pack(pady=20)
        
        olustur_btn = ctk.CTkButton(
            buton_frame,
            text="✅ PDF Oluştur",
            command=lambda: [secenekler_pencere.destroy(), self.pdf_olustur()],
            fg_color="#1f6aa5",
            hover_color="#144870",
            width=150,
            height=40
        )
        olustur_btn.pack(side="left", padx=5)
        
        iptal_btn = ctk.CTkButton(
            buton_frame,
            text="❌ İptal",
            command=secenekler_pencere.destroy,
            fg_color="#d32f2f",
            hover_color="#9a0007",
            width=150,
            height=40
        )
        iptal_btn.pack(side="left", padx=5)
    
    def secili_desenlerden_pdf_secenekleri_goster(self):
        """Seçili desenlerden PDF için filigran seçme penceresi"""
        if not self.secili_desenler:
            messagebox.showwarning("Uyarı", "Lütfen PDF'e eklemek için desenler seçin")
            return
        secenekler_pencere = ctk.CTkToplevel(self)
        secenekler_pencere.title("PDF Seçenekleri")
        secenekler_pencere.geometry("400x250")
        secenekler_pencere.resizable(False, False)
        secenekler_pencere.transient(self)
        secenekler_pencere.grab_set()
        
        # Ana pencereyi ortasında konumlandır
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 125
        secenekler_pencere.geometry(f"400x250+{x}+{y}")
        
        baslik = ctk.CTkLabel(
            secenekler_pencere,
            text="📄 Seçili Desenlerden PDF",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        baslik.pack(pady=20)
        filigran_frame = ctk.CTkFrame(secenekler_pencere)
        filigran_frame.pack(pady=20, padx=30, fill="x")
        filigran_label = ctk.CTkLabel(
            filigran_frame,
            text="Filigran Ekle:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        filigran_label.pack(side="left", padx=10)
        filigran_switch = ctk.CTkSwitch(
            filigran_frame,
            text="ORHAN KARAKOÇ TEKSTİL",
            variable=self.filigran_var,
            font=ctk.CTkFont(size=12)
        )
        filigran_switch.pack(side="left", padx=10)
        aciklama = ctk.CTkLabel(
            secenekler_pencere,
            text="Filigran açıksa her sayfaya\n'ORHAN KARAKOÇ TEKSTİL' yazısı eklenir",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        aciklama.pack(pady=10)
        buton_frame = ctk.CTkFrame(secenekler_pencere, fg_color="transparent")
        buton_frame.pack(pady=20)
        
        olustur_btn = ctk.CTkButton(
            buton_frame,
            text="✅ PDF Oluştur",
            command=lambda: [secenekler_pencere.destroy(), self.secili_desenlerden_pdf_olustur()],
            fg_color="#1f6aa5",
            hover_color="#144870",
            width=150,
            height=40
        )
        olustur_btn.pack(side="left", padx=5)
        
        iptal_btn = ctk.CTkButton(
            buton_frame,
            text="❌ İptal",
            command=secenekler_pencere.destroy,
            fg_color="#d32f2f",
            hover_color="#9a0007",
            width=150,
            height=40
        )
        iptal_btn.pack(side="left", padx=5)
    
    def tam_ekran_goster(self):
        """Deseni tam ekranda göster"""
        try:
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            
            if not self.aktif_klasor:
                messagebox.showwarning("Uyarı", "Lütfen önce bir klasör seçin")
                return
                
            if self.aktif_klasor not in aktif_desenler:
                messagebox.showwarning("Uyarı", f"'{self.aktif_klasor}' klasörü bulunamadı")
                return
                
            desenler = aktif_desenler[self.aktif_klasor]
            if not desenler or self.aktif_desen_index >= len(desenler):
                messagebox.showwarning("Uyarı", "Gösterilecek desen yok")
                return
                
            desen = desenler[self.aktif_desen_index]
            
            # Dosya yolunu kontrol et
            dosya_yolu = desen['dosya']
            if isinstance(dosya_yolu, str):
                dosya_yolu = Path(dosya_yolu)
            
            if not dosya_yolu.exists():
                messagebox.showerror("Hata", f"Dosya bulunamadı: {dosya_yolu.name}")
                return
                
        except Exception as e:
            messagebox.showerror("Hata", f"Tam ekran gösterim hatası: {str(e)}")
            import traceback
            traceback.print_exc()
            return
            
        self.tam_ekran_pencere = ctk.CTkToplevel(self)
        self.tam_ekran_pencere.title("Tam Ekran Önizleme")
        self.tam_ekran_pencere.attributes('-fullscreen', True)
        self.tam_ekran_pencere.attributes('-topmost', True)  # Her zaman üstte
        self.tam_ekran_pencere.configure(fg_color="black")
        
        # Focus'u pencereye zorla - çoklu yöntem
        self.tam_ekran_pencere.focus_set()
        self.tam_ekran_pencere.focus_force()
        # Pencere tamamen yüklendikten sonra tekrar focus al
        self.tam_ekran_pencere.after(100, lambda: self.tam_ekran_pencere.focus_force())
        
        # Ana frame oluştur
        ana_frame = ctk.CTkFrame(self.tam_ekran_pencere, fg_color="black")
        ana_frame.pack(fill="both", expand=True)
        ana_frame.grid_rowconfigure(0, weight=1)
        ana_frame.grid_columnconfigure(0, weight=1)
        
        # Önceki/Sonraki yazıları için label'lar oluştur
        self.tam_ekran_sol_label = ctk.CTkLabel(
            self.tam_ekran_pencere,
            text="⬅️ ÖNCEKİ",
            font=ctk.CTkFont(size=32, weight="bold"),
            fg_color="black",
            text_color="white"
        )
        
        self.tam_ekran_sag_label = ctk.CTkLabel(
            self.tam_ekran_pencere,
            text="SONRAKİ ➡️",
            font=ctk.CTkFont(size=32, weight="bold"),
            fg_color="black",
            text_color="white"
        )
        
        # Event handler fonksiyonları
        def kapat(e=None):
            self.tam_ekran_kapat()
            return "break"
        
        def onceki(e=None):
            print("DEBUG: Önceki tuşuna basıldı")  # Debug için
            self._tam_ekran_onceki_goster()
            return "break"
        
        def sonraki(e=None):
            print("DEBUG: Sonraki tuşuna basıldı")  # Debug için
            self._tam_ekran_sonraki_goster()
            return "break"
        
        # Pencereye event binding'leri ekle - hem normal bind hem bind_all kullan
        self.tam_ekran_pencere.bind("<Escape>", kapat)
        self.tam_ekran_pencere.bind("<KeyPress-Left>", onceki)
        self.tam_ekran_pencere.bind("<KeyPress-Right>", sonraki)
        self.tam_ekran_pencere.bind("<Left>", onceki)  # Alternatif
        self.tam_ekran_pencere.bind("<Right>", sonraki)  # Alternatif
        self.tam_ekran_pencere.bind("<MouseWheel>", self._tam_ekran_scroll)
        self.tam_ekran_pencere.bind("<Button-4>", onceki)  # Linux scroll up
        self.tam_ekran_pencere.bind("<Button-5>", sonraki)  # Linux scroll down
        
        # Global binding - tüm pencereye yayıl
        self.tam_ekran_pencere.bind_all("<Left>", onceki)
        self.tam_ekran_pencere.bind_all("<Right>", sonraki)
        self.tam_ekran_pencere.bind_all("<Escape>", kapat)
        
        try:
            from PIL import Image
            img = Image.open(dosya_yolu)  # Kontrol edilmiş dosya yolunu kullan
            ekran_genislik = self.tam_ekran_pencere.winfo_screenwidth()
            ekran_yukseklik = self.tam_ekran_pencere.winfo_screenheight()
            
            # Tam ekran için daha düşük çözünürlük
            max_genislik = min(1200, ekran_genislik - 100)  # Maksimum 1200px
            max_yukseklik = min(900, ekran_yukseklik - 100)  # Maksimum 900px
            img.thumbnail((max_genislik, max_yukseklik), Image.Resampling.LANCZOS)
            
            ctk_img = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=img.size
            )
            img_label = ctk.CTkLabel(
                ana_frame,
                image=ctk_img,
                text=""
            )
            img_label.grid(row=0, column=0)
            img_label.image = ctk_img
            
            # Resim label'ına da tıklama eventi ekle
            img_label.bind("<Button-1>", kapat)
            
            # Bilgi metni güncellendi - aktif kategori desenlerini kullan
            aktif_desenler = self.get_aktif_kategori_desenler()
            desenler = aktif_desenler[self.aktif_klasor]
            pozisyon = f"{self.aktif_desen_index + 1}/{len(desenler)}"
            bilgi_text = f"{desen['ad']} - {img.width}x{img.height} - {pozisyon} - ESC/Tıkla=Kapat | ←→/Scroll=Geçiş"
            bilgi_label = ctk.CTkLabel(
                self.tam_ekran_pencere,
                text=bilgi_text,
                font=ctk.CTkFont(size=16, weight="bold"),
                fg_color="black",
                text_color="white"
            )
            bilgi_label.place(relx=0.5, rely=0.02, anchor="center")
        except Exception as e:
            self.tam_ekran_kapat()
            messagebox.showerror("Hata", f"Tam ekran gösterim hatası: {str(e)}")
    
    def _tam_ekran_scroll(self, event):
        """Mouse scroll wheel ile tam ekranda desen değiştir"""
        try:
            # Event tipine göre yön belirle
            if event.type == "38":  # MouseWheel event
                if event.delta > 0:  # Scroll up - önceki
                    self._tam_ekran_onceki_goster()
                else:  # Scroll down - sonraki
                    self._tam_ekran_sonraki_goster()
            elif event.num == 4:  # Linux Button-4 (scroll up)
                self._tam_ekran_onceki_goster()
            elif event.num == 5:  # Linux Button-5 (scroll down)
                self._tam_ekran_sonraki_goster()
            return "break"  # Event propagation'u durdur
        except Exception as e:
            print(f"Tam ekran scroll hatası: {e}")
            return "break"
    
    def _tam_ekran_onceki_goster(self):
        """Tam ekranda önceki desene geç ve 'Önceki' yazısını göster"""
        try:
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            
            if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
                return
            desenler = aktif_desenler[self.aktif_klasor]
            if self.aktif_desen_index > 0:
                # Sol tarafta "Önceki" yazısını göster
                if hasattr(self, 'tam_ekran_sol_label'):
                    try:
                        self.tam_ekran_sol_label.place(relx=0.1, rely=0.5, anchor="center")
                        # 800ms sonra gizle
                        self.after(800, self._gizle_sol_label)
                    except:
                        pass
                
                # Deseni değiştir
                self.tam_ekran_onceki()
        except Exception as e:
            print(f"Tam ekran önceki göster hatası: {e}")
    
    def _tam_ekran_sonraki_goster(self):
        """Tam ekranda sonraki desene geç ve 'Sonraki' yazısını göster"""
        try:
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            
            if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
                return
            desenler = aktif_desenler[self.aktif_klasor]
            if self.aktif_desen_index < len(desenler) - 1:
                # Sağ tarafta "Sonraki" yazısını göster
                if hasattr(self, 'tam_ekran_sag_label'):
                    try:
                        self.tam_ekran_sag_label.place(relx=0.9, rely=0.5, anchor="center")
                        # 800ms sonra gizle
                        self.after(800, self._gizle_sag_label)
                    except:
                        pass
                
                # Deseni değiştir
                self.tam_ekran_sonraki()
        except Exception as e:
            print(f"Tam ekran sonraki göster hatası: {e}")
    
    def _gizle_sol_label(self):
        """Sol label'ı gizle"""
        try:
            if hasattr(self, 'tam_ekran_sol_label'):
                self.tam_ekran_sol_label.place_forget()
        except:
            pass
    
    def _gizle_sag_label(self):
        """Sağ label'ı gizle"""
        try:
            if hasattr(self, 'tam_ekran_sag_label'):
                self.tam_ekran_sag_label.place_forget()
        except:
            pass
    
    def tam_ekran_onceki(self):
        """Tam ekranda önceki desene geç"""
        try:
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            
            if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
                return
            desenler = aktif_desenler[self.aktif_klasor]
            if self.aktif_desen_index > 0:
                self.aktif_desen_index -= 1
                self.deseni_goster()  # Ana menüdeki deseni de güncelle
                self.ayarlari_kaydet()
                # Tam ekranı yeniden yükle
                if self.tam_ekran_pencere and self.tam_ekran_pencere.winfo_exists():
                    self._tam_ekran_yenile()
        except Exception as e:
            print(f"Tam ekran önceki hatası: {e}")
    
    def tam_ekran_sonraki(self):
        """Tam ekranda sonraki desene geç"""
        try:
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            
            if not self.aktif_klasor or self.aktif_klasor not in aktif_desenler:
                return
            desenler = aktif_desenler[self.aktif_klasor]
            if self.aktif_desen_index < len(desenler) - 1:
                self.aktif_desen_index += 1
                self.deseni_goster()  # Ana menüdeki deseni de güncelle
                self.ayarlari_kaydet()
                # Tam ekranı yenile
                if self.tam_ekran_pencere and self.tam_ekran_pencere.winfo_exists():
                    self._tam_ekran_yenile()
        except Exception as e:
            print(f"Tam ekran sonraki hatası: {e}")
    
    def _tam_ekran_yenile(self):
        """Tam ekran penceresini yeniden yükle (kapatmadan)"""
        try:
            if not self.tam_ekran_pencere or not self.tam_ekran_pencere.winfo_exists():
                return
            
            # Aktif kategoriye göre desenler al
            aktif_desenler = self.get_aktif_kategori_desenler()
            desenler = aktif_desenler[self.aktif_klasor]
            desen = desenler[self.aktif_desen_index]
            
            # Mevcut tüm widget'ları temizle
            for widget in self.tam_ekran_pencere.winfo_children():
                widget.destroy()
            
            # Global binding'leri temizle
            self.tam_ekran_pencere.unbind_all("<Left>")
            self.tam_ekran_pencere.unbind_all("<Right>")
            self.tam_ekran_pencere.unbind_all("<Escape>")
            
            # Focus'u tekrar zorla - çoklu yöntem
            self.tam_ekran_pencere.focus_set()
            self.tam_ekran_pencere.focus_force()
            self.tam_ekran_pencere.after(50, lambda: self.tam_ekran_pencere.focus_force())
            
            # Yeni içerik oluştur
            ana_frame = ctk.CTkFrame(self.tam_ekran_pencere, fg_color="black")
            ana_frame.pack(fill="both", expand=True)
            ana_frame.grid_rowconfigure(0, weight=1)
            ana_frame.grid_columnconfigure(0, weight=1)
            
            # Önceki/Sonraki yazıları için label'lar yeniden oluştur
            self.tam_ekran_sol_label = ctk.CTkLabel(
                self.tam_ekran_pencere,
                text="⬅️ ÖNCEKİ",
                font=ctk.CTkFont(size=32, weight="bold"),
                fg_color="black",
                text_color="white"
            )
            
            self.tam_ekran_sag_label = ctk.CTkLabel(
                self.tam_ekran_pencere,
                text="SONRAKİ ➡️",
                font=ctk.CTkFont(size=32, weight="bold"),
                fg_color="black",
                text_color="white"
            )
            
            # Klavye ve fare binding'lerini yeniden bağla
            def kapat(e=None):
                self.tam_ekran_kapat()
                return "break"
            
            def onceki(e=None):
                print("DEBUG: Önceki tuşuna basıldı (yenileme)")  # Debug için
                self._tam_ekran_onceki_goster()
                return "break"
            
            def sonraki(e=None):
                print("DEBUG: Sonraki tuşuna basıldı (yenileme)")  # Debug için
                self._tam_ekran_sonraki_goster()
                return "break"
            
            # Pencereye bağla - hem normal hem bind_all
            self.tam_ekran_pencere.bind("<Escape>", kapat)
            self.tam_ekran_pencere.bind("<KeyPress-Left>", onceki)
            self.tam_ekran_pencere.bind("<KeyPress-Right>", sonraki)
            self.tam_ekran_pencere.bind("<Left>", onceki)
            self.tam_ekran_pencere.bind("<Right>", sonraki)
            self.tam_ekran_pencere.bind("<MouseWheel>", self._tam_ekran_scroll)
            self.tam_ekran_pencere.bind("<Button-4>", onceki)  # Linux scroll up
            self.tam_ekran_pencere.bind("<Button-5>", sonraki)  # Linux scroll down
            
            # Global binding - tüm pencereye yayıl
            self.tam_ekran_pencere.bind_all("<Left>", onceki)
            self.tam_ekran_pencere.bind_all("<Right>", sonraki)
            self.tam_ekran_pencere.bind_all("<Escape>", kapat)
            
            # Yeni resmi yükle
            from PIL import Image
            dosya_yolu = desen['dosya']
            if isinstance(dosya_yolu, str):
                dosya_yolu = Path(dosya_yolu)
            img = Image.open(dosya_yolu)
            ekran_genislik = self.tam_ekran_pencere.winfo_screenwidth()
            ekran_yukseklik = self.tam_ekran_pencere.winfo_screenheight()
            
            # Tam ekran için daha düşük çözünürlük
            max_genislik = min(1200, ekran_genislik - 100)  # Maksimum 1200px
            max_yukseklik = min(900, ekran_yukseklik - 100)  # Maksimum 900px
            img.thumbnail((max_genislik, max_yukseklik), Image.Resampling.LANCZOS)
            
            ctk_img = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=img.size
            )
            img_label = ctk.CTkLabel(
                ana_frame,
                image=ctk_img,
                text=""
            )
            img_label.grid(row=0, column=0)
            img_label.image = ctk_img
            
            # Resim label'ına da tıklama eventi ekle
            img_label.bind("<Button-1>", kapat)
            
            # Bilgi metni güncelle
            pozisyon = f"{self.aktif_desen_index + 1}/{len(desenler)}"
            bilgi_text = f"{desen['ad']} - {img.width}x{img.height} - {pozisyon} - ESC/Tıkla=Kapat | ←→/Scroll=Geçiş"
            bilgi_label = ctk.CTkLabel(
                self.tam_ekran_pencere,
                text=bilgi_text,
                font=ctk.CTkFont(size=16, weight="bold"),
                fg_color="black",
                text_color="white"
            )
            bilgi_label.place(relx=0.5, rely=0.02, anchor="center")
            
        except Exception as e:
            print(f"Tam ekran yenileme hatası: {e}")
    
    def tam_ekran_kapat(self):
        """Tam ekran penceresini kapat"""
        try:
            if self.tam_ekran_pencere and self.tam_ekran_pencere.winfo_exists():
                # Global binding'leri temizle
                try:
                    self.tam_ekran_pencere.unbind_all("<Left>")
                    self.tam_ekran_pencere.unbind_all("<Right>")
                    self.tam_ekran_pencere.unbind_all("<Escape>")
                except:
                    pass
                self.tam_ekran_pencere.destroy()
        except Exception as e:
            print(f"Tam ekran kapatma hatası: {e}")
        finally:
            self.tam_ekran_pencere = None
    
    def _maximize_window(self):
        """Pencereyi maximize et - başlangıçta çağrılır"""
        try:
            self.state("zoomed")  # Windows'ta maximize
        except:
            try:
                # Fallback: ekran boyutuna ayarla
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                self.geometry(f"{sw}x{sh}+0+0")
            except:
                pass
    
    def observer_baslat(self):
        """JPG izleyiciyi başlat - aktif kategoriye göre"""
        try:
            # Lazy import - sadece kullanılacaksa
            if self.observer is None:
                from watchdog.observers import Observer
                self.observer = Observer()
            
            # Önceki observer'ı durdur
            if self.observer_running:
                self.observer_durdur()
            
            # Aktif kategorinin ana klasörünü izle
            ana_klasor = None
            if self.aktif_kategori == "Desenler" and self.desenler_ana_klasor:
                ana_klasor = self.desenler_ana_klasor
            elif self.aktif_kategori == "Varyantlar" and self.varyantlar_ana_klasor:
                ana_klasor = self.varyantlar_ana_klasor
            
            if ana_klasor and Path(ana_klasor).exists():
                # Observer'ı başlat
                self.observer.schedule(self.jpg_watcher, str(ana_klasor), recursive=False)
                self.observer.start()
                self.observer_running = True
                print(f"📂 JPG izleyici başlatıldı: {ana_klasor}")
        except Exception as e:
            print(f"Observer başlatılamadı: {e}")
    
    def observer_durdur(self):
        """JPG izleyiciyi durdur"""
        try:
            if self.observer_running and self.observer:
                self.observer.stop()
                self.observer.join(timeout=2)
                # Yeni observer oluştur
                from watchdog.observers import Observer
                self.observer = Observer()
                self.observer_running = False
                print("🛑 JPG izleyici durduruldu")
        except Exception as e:
            print(f"Observer durdurulamadı: {e}")
    
    def ana_klasor_jpgleri_boyutlandir(self):
        """Ana klasördeki tüm JPG dosyalarını 1200x900'e boyutlandır"""
        # Aktif kategorinin ana klasörünü al
        ana_klasor = None
        if self.aktif_kategori == "Desenler" and self.desenler_ana_klasor:
            ana_klasor = self.desenler_ana_klasor
        elif self.aktif_kategori == "Varyantlar" and self.varyantlar_ana_klasor:
            ana_klasor = self.varyantlar_ana_klasor
        
        if not ana_klasor:
            messagebox.showwarning("Uyarı", "Lütfen önce bir ana klasör seçin!")
            return
        
        ana_klasor = Path(ana_klasor)
        if not ana_klasor.exists():
            messagebox.showerror("Hata", "Ana klasör bulunamadı!")
            return
        
        # Progress penceresi oluştur
        progress_win = ctk.CTkToplevel(self)
        progress_win.title("JPG Boyutlandırma")
        progress_win.geometry("600x250")
        progress_win.transient(self)
        progress_win.grab_set()
        
        # Progress frame
        progress_frame = ctk.CTkFrame(progress_win)
        progress_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Durum label
        durum_label = ctk.CTkLabel(
            progress_frame,
            text="Dosyalar taranıyor...",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        durum_label.pack(pady=(10, 5))
        
        # Progress bar
        progress_bar = ctk.CTkProgressBar(progress_frame, width=500)
        progress_bar.pack(pady=10)
        progress_bar.set(0)
        
        # Detay label
        detay_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        detay_label.pack(pady=5)
        
        # Sayaç label
        sayac_label = ctk.CTkLabel(
            progress_frame,
            text="0 / 0",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        sayac_label.pack(pady=10)
        
        self.update()
        
        # Ana klasör ve ALT KLASÖRLERDEKİ JPG dosyalarını bul
        durum_label.configure(text="📂 Dosyalar taranıyor...")
        self.update()
        
        jpg_dosyalari = []
        for dosya in ana_klasor.rglob('*'):  # rglob ile recursive tarama
            if dosya.is_file() and dosya.suffix.lower() in ['.jpg', '.jpeg']:
                jpg_dosyalari.append(dosya)
        
        progress_win.destroy()
        
        if not jpg_dosyalari:
            messagebox.showinfo("Bilgi", "Ana klasör ve alt klasörlerde JPG dosyası bulunamadı!")
            return
        
        # Onay al
        cevap = messagebox.askyesno(
            "Onay",
            f"{len(jpg_dosyalari)} adet JPG dosyası bulundu.\n\n"
            f"Tüm dosyalar 1200x900px maksimum boyuta getirilecek.\n"
            f"Devam etmek istiyor musunuz?"
        )
        
        if not cevap:
            return
        
        # Progress penceresi yeniden oluştur
        progress_win = ctk.CTkToplevel(self)
        progress_win.title("JPG Boyutlandırma")
        progress_win.geometry("600x250")
        progress_win.transient(self)
        progress_win.grab_set()
        
        # Progress frame
        progress_frame = ctk.CTkFrame(progress_win)
        progress_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Durum label
        durum_label = ctk.CTkLabel(
            progress_frame,
            text="İşlem yapılıyor...",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        durum_label.pack(pady=(10, 5))
        
        # Progress bar
        progress_bar = ctk.CTkProgressBar(progress_frame, width=500)
        progress_bar.pack(pady=10)
        progress_bar.set(0)
        
        # Detay label
        detay_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        detay_label.pack(pady=5)
        
        # Sayaç label
        sayac_label = ctk.CTkLabel(
            progress_frame,
            text=f"0 / {len(jpg_dosyalari)}",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        sayac_label.pack(pady=10)
        
        self.update()
        
        # İşlem başlat
        basarili = 0
        atlanmis = 0
        hatali = 0
        
        for idx, dosya in enumerate(jpg_dosyalari, 1):
            try:
                # Progress güncelle
                progress = idx / len(jpg_dosyalari)
                progress_bar.set(progress)
                sayac_label.configure(text=f"{idx} / {len(jpg_dosyalari)}")
                detay_label.configure(text=f"📄 {dosya.name}")
                self.update()
                
                # Resmi yükle
                img = Image.open(dosya)
                original_width, original_height = img.size
                
                # Zaten küçükse atla
                if original_width <= 1200 and original_height <= 900:
                    atlanmis += 1
                    print(f"⏭ Atlandı (zaten küçük): {dosya.name} ({original_width}x{original_height})")
                    continue
                
                # En-boy oranını koru
                ratio = min(1200 / original_width, 900 / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                # Boyutlandır
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Geçici dosyaya kaydet
                temp_path = dosya.with_suffix('.tmp')
                img_resized.save(temp_path, 'JPEG', quality=95, optimize=True)
                
                # Orijinali değiştir
                os.replace(temp_path, dosya)
                
                basarili += 1
                print(f"✅ Boyutlandırıldı: {dosya.name} ({original_width}x{original_height} → {new_width}x{new_height})")
                
            except Exception as e:
                hatali += 1
                print(f"❌ Hata: {dosya.name} - {e}")
        
        # Progress penceresini kapat
        progress_win.destroy()
        
        # Sonuç mesajı
        mesaj = f"İşlem tamamlandı!\n\n"
        mesaj += f"✅ Başarılı: {basarili}\n"
        mesaj += f"⏭ Atlanmış (zaten küçük): {atlanmis}\n"
        mesaj += f"❌ Hatalı: {hatali}"
        
        messagebox.showinfo("Sonuç", mesaj)
        
        # Klasörü yeniden yükle
        if basarili > 0:
            self.klasoru_yukle(self.aktif_kategori)
    
    def destroy(self):
        """Pencere kapatılırken observer'ı durdur"""
        self.observer_durdur()
        super().destroy()

if __name__ == "__main__":
    app = DesenYonetimSistemi()
    app.mainloop()