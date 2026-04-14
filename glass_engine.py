# glass_engine.py — Ultra 3D Glass DLC for Core Plugin
# Author: @project_BAJIbTEP & AI
# Version: 3.5.1 (Ultra 3D Release - JNI Color Fix)

VERSION = "3.5.1"

import math
import random

from android_utils import log
from hook_utils import find_class
from java import jarray, jint

# --- Базовые классы Android ---
Paint            = find_class("android.graphics.Paint")
Canvas           = find_class("android.graphics.Canvas")
Drawable         = find_class("android.graphics.drawable.Drawable")
RectF            = find_class("android.graphics.RectF")
Color            = find_class("android.graphics.Color")
GradientDrawable = find_class("android.graphics.drawable.GradientDrawable")
LayerDrawable    = find_class("android.graphics.drawable.LayerDrawable")
BitmapDrawable   = find_class("android.graphics.drawable.BitmapDrawable")
Bitmap           = find_class("android.graphics.Bitmap")
Shader           = find_class("android.graphics.Shader")
ShaderTileMode   = find_class("android.graphics.Shader$TileMode")
View             = find_class("android.view.View")
AndroidUtilities = find_class("org.telegram.messenger.AndroidUtilities")
Theme            = find_class("org.telegram.ui.ActionBar.Theme")
Build            = find_class("android.os.Build$VERSION")

try:
    RenderEffect = find_class("android.graphics.RenderEffect")
    _HAS_RENDER_EFFECT = True
except Exception:
    RenderEffect = None
    _HAS_RENDER_EFFECT = False

try:
    BlendMode = find_class("android.graphics.BlendMode")
    _HAS_BLEND_MODE = True
except Exception:
    BlendMode = None
    _HAS_BLEND_MODE = False

class GlassEngine:
    GLASS_FROSTED = 0
    GLASS_GLOSSY  = 1
    GLASS_LIQUID  = 2
    GLASS_RIBBED  = 3

    RUNTIME = {
        "bg_blur":          22,
        "bg_dim":           0.14,
        "border_alpha":     34,
        "highlight_alpha":  88,
    }

    _NOISE_CACHE = None
    _LINES_CACHE = None

    @staticmethod
    def configure(cfg: dict):
        try:
            if cfg:
                GlassEngine.RUNTIME.update(cfg)
        except Exception:
            pass

    @staticmethod
    def _clamp(v, lo, hi):
        try: return max(lo, min(hi, float(v)))
        except: return lo

    @staticmethod
    def _s32(val):
        """Конвертирует Python int в подписанный 32-битный int для Java (решение проблемы цветов)"""
        val = int(val) & 0xFFFFFFFF
        return val if val < 0x80000000 else val - 0x100000000

    @staticmethod
    def _alpha(color_int):
        return (int(color_int) >> 24) & 0xFF

    @staticmethod
    def _with_alpha(color_int, alpha):
        alpha = int(GlassEngine._clamp(alpha, 0, 255))
        return (int(color_int) & 0x00FFFFFF) | (alpha << 24)

    # =========================================================
    # ГЕНЕРАТОРЫ ТЕКСТУР (Noise / Grain / Ribbed)
    # =========================================================
    @staticmethod
    def _build_noise_bitmap(size=128, intensity=25):
        """Генерирует бесшовную текстуру матового шума (Frosted Glass grain)"""
        if GlassEngine._NOISE_CACHE:
            return GlassEngine._NOISE_CACHE
        
        try:
            bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
            pixels = jarray(jint)(size * size)
            for i in range(size * size):
                val = random.randint(0, 255)
                alpha = random.randint(0, intensity)
                # Обязательно конвертируем цвет в Signed 32-bit
                pixels[i] = GlassEngine._s32(Color.argb(alpha, val, val, val))
            bmp.setPixels(pixels, 0, size, 0, 0, size, size)
            GlassEngine._NOISE_CACHE = bmp
            return bmp
        except Exception as e:
            log(f"Noise gen error: {e}")
            return None

    @staticmethod
    def _build_lines_bitmap(size=64):
        """Генерирует диагональные линии для ребристого стекла (Ribbed)"""
        if GlassEngine._LINES_CACHE:
            return GlassEngine._LINES_CACHE
        try:
            bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
            canvas = Canvas(bmp)
            p = Paint()
            p.setAntiAlias(True)
            p.setColor(GlassEngine._s32(Color.argb(40, 255, 255, 255)))
            p.setStrokeWidth(float(size) / 8.0)
            p.setStrokeCap(Paint.Cap.SQUARE)
            
            canvas.drawLine(0, 0, size, size, p)
            canvas.drawLine(size, 0, size*2, size, p)
            canvas.drawLine(-size, 0, 0, size, p)
            
            GlassEngine._LINES_CACHE = bmp
            return bmp
        except Exception as e:
            log(f"Lines gen error: {e}")
            return None

    # =========================================================
    # ФОЛЛБЭК ДЛЯ ОБОЕВ (На старых Android)
    # =========================================================
    @staticmethod
    def _draw_center_crop(drawable, canvas, width, height):
        try: iw = int(drawable.getIntrinsicWidth())
        except: iw = -1
        try: ih = int(drawable.getIntrinsicHeight())
        except: ih = -1
        
        if iw <= 0 or ih <= 0:
            try:
                b = drawable.getBounds()
                if b.width() > 0 and b.height() > 0:
                    iw, ih = int(b.width()), int(b.height())
            except: pass
            
        if iw <= 0 or ih <= 0:
            iw, ih = width, height
            
        scale = max(float(width) / float(iw), float(height) / float(ih))
        dw, dh = int(iw * scale), int(ih * scale)
        left, top = int((width - dw) / 2), int((height - dh) / 2)
        try:
            drawable.setBounds(left, top, left + dw, top + dh)
            drawable.draw(canvas)
        except: pass

    @staticmethod
    def _build_wallpaper_bitmap(context, width, height, blur_px, dim_alpha):
        bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bmp)
        try: canvas.drawColor(GlassEngine._s32(Color.BLACK))
        except: pass
        
        try:
            wallpaper = Theme.getCachedWallpaperNonBlocking()
            if wallpaper:
                w = wallpaper.mutate() if hasattr(wallpaper, "mutate") else wallpaper
                GlassEngine._draw_center_crop(w, canvas, width, height)
        except Exception: pass

        if blur_px > 0:
            try:
                factor = max(1.0, min(24.0, 1.0 + blur_px * 0.5))
                target_w = max(1, int(width / factor))
                target_h = max(1, int(height / factor))
                small = Bitmap.createScaledBitmap(bmp, target_w, target_h, True)
                bmp = Bitmap.createScaledBitmap(small, width, height, True)
            except Exception: pass

        if dim_alpha > 0:
            try:
                dim_canvas = Canvas(bmp)
                paint = Paint()
                paint.setColor(GlassEngine._s32(GlassEngine._with_alpha(Color.BLACK, dim_alpha)))
                dim_canvas.drawRect(0, 0, width, height, paint)
            except: pass
            
        return bmp

    # =========================================================
    # ГЛАВНЫЙ РЕНДЕР (ULTRA 3D COMPOSITOR)
    # =========================================================
    @staticmethod
    def apply(view, context, glass_type, color_int, radius_dp, blur_radius=16, use_wallpaper=False):
        try:
            DrawableArr = jarray(Drawable)
            layers =[]
            radius_px = float(AndroidUtilities.dp(max(0, int(radius_dp))))
            high_alpha = int(GlassEngine._clamp(GlassEngine.RUNTIME.get("highlight_alpha", 88), 0, 255))
            border_alpha = int(GlassEngine._clamp(GlassEngine.RUNTIME.get("border_alpha", 34), 0, 255))

            if use_wallpaper:
                try:
                    sdk = int(Build.SDK_INT)
                    if sdk < 31 or not _HAS_RENDER_EFFECT:
                        w, h = int(view.getWidth()), int(view.getHeight())
                        if w > 0 and h > 0:
                            dim = int(GlassEngine.RUNTIME.get("bg_dim", 0.14) * 255)
                            blur = int(GlassEngine.RUNTIME.get("bg_blur", 22))
                            bg_bmp = GlassEngine._build_wallpaper_bitmap(context, w, h, blur, dim)
                            layers.append(BitmapDrawable(context.getResources(), bg_bmp))
                except Exception: pass

            # 2. БАЗОВЫЙ ЦВЕТ СТЕКЛА
            base_gd = GradientDrawable()
            base_gd.setCornerRadius(radius_px)
            base_gd.setColor(GlassEngine._s32(color_int))
            layers.append(base_gd)

            # 3. ТЕКСТУРЫ (Шум или Полосы)
            if not use_wallpaper:
                tex_bmp = None
                if glass_type == GlassEngine.GLASS_RIBBED:
                    tex_bmp = GlassEngine._build_lines_bitmap()
                else:
                    intensity = 40 if glass_type == GlassEngine.GLASS_LIQUID else 25
                    tex_bmp = GlassEngine._build_noise_bitmap(intensity=intensity)

                if tex_bmp:
                    tex_draw = BitmapDrawable(context.getResources(), tex_bmp)
                    tex_draw.setTileModeXY(ShaderTileMode.REPEAT, ShaderTileMode.REPEAT)
                    if _HAS_BLEND_MODE:
                        try: tex_draw.setBlendMode(BlendMode.OVERLAY)
                        except: pass
                    layers.append(tex_draw)

            # 4. 3D ОБЪЕМ И БЛИКИ (Внутренняя подсветка)
            if not use_wallpaper:
                glow_main = GradientDrawable()
                glow_main.setCornerRadius(radius_px)
                glow_main.setOrientation(GradientDrawable.Orientation.TL_BR)
                
                if glass_type == GlassEngine.GLASS_GLOSSY:
                    glow_main.setColors(jarray(jint)([
                        GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, int(high_alpha * 1.2))),
                        GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, int(high_alpha * 0.4))),
                        GlassEngine._s32(Color.TRANSPARENT), 
                        GlassEngine._s32(Color.TRANSPARENT),
                        GlassEngine._s32(GlassEngine._with_alpha(Color.BLACK, int(high_alpha * 0.6)))
                    ]))
                else:
                    glow_main.setColors(jarray(jint)([
                        GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, high_alpha)),
                        GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, int(high_alpha * 0.15))),
                        GlassEngine._s32(Color.TRANSPARENT), 
                        GlassEngine._s32(Color.TRANSPARENT),
                        GlassEngine._s32(GlassEngine._with_alpha(Color.BLACK, int(high_alpha * 0.4)))
                    ]))
                layers.append(glow_main)

                if glass_type in (GlassEngine.GLASS_GLOSSY, GlassEngine.GLASS_LIQUID):
                    glow_sec = GradientDrawable()
                    glow_sec.setCornerRadius(radius_px)
                    glow_sec.setOrientation(GradientDrawable.Orientation.BOTTOM_TOP)
                    glow_sec.setColors(jarray(jint)([
                        GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, int(high_alpha * 0.5))),
                        GlassEngine._s32(Color.TRANSPARENT), 
                        GlassEngine._s32(Color.TRANSPARENT)
                    ]))
                    layers.append(glow_sec)

            # 5. ОСТРЫЕ ГРАНИ (Рамка)
            if border_alpha > 0 and not use_wallpaper:
                rim = GradientDrawable()
                rim.setCornerRadius(radius_px)
                rim.setColor(GlassEngine._s32(Color.TRANSPARENT))
                rim.setStroke(AndroidUtilities.dp(1), GlassEngine._s32(GlassEngine._with_alpha(Color.WHITE, border_alpha)))
                layers.append(rim)

            # СБОРКА СЛОЕВ
            layer_drawable = LayerDrawable(DrawableArr(layers))
            
            try: view.setClipToOutline(True)
            except Exception: pass
            
            try: view.setBackground(layer_drawable)
            except Exception: view.setBackgroundDrawable(layer_drawable)

        except Exception as e:
            log(f"GlassEngine ULTRA apply error: {e}")
