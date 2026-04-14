# glass_engine.py  —  Glass DLC for Core Plugin by BAJIbTEP
# Этот файл лежит на GitHub и скачивается по кнопке из плагина.
# Версия здесь используется для проверки обновлений.

VERSION = "1.0.0"

import math

from android_utils import log
from hook_utils import find_class

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

from java import jarray, jint


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

    # ── утилиты ──────────────────────────────────────────────────────────────

    @staticmethod
    def configure(cfg: dict):
        try:
            if cfg:
                GlassEngine.RUNTIME.update(cfg)
        except Exception:
            pass

    @staticmethod
    def _clamp(v, lo, hi):
        try:
            v = float(v)
        except Exception:
            v = lo
        return max(lo, min(hi, v))

    @staticmethod
    def _alpha(color_int):
        return (int(color_int) >> 24) & 0xFF

    @staticmethod
    def _with_alpha(color_int, alpha):
        alpha = int(GlassEngine._clamp(alpha, 0, 255))
        return (int(color_int) & 0x00FFFFFF) | (alpha << 24)

    # ── фоновый bitmap (обои, масштаб, затемнение) ────────────────────────

    @staticmethod
    def _draw_center_crop(drawable, canvas, width, height):
        try:
            iw = int(drawable.getIntrinsicWidth())
        except Exception:
            iw = -1
        try:
            ih = int(drawable.getIntrinsicHeight())
        except Exception:
            ih = -1
        if iw <= 0 or ih <= 0:
            try:
                bmp = drawable.getBitmap()
                if bmp is not None:
                    iw = int(bmp.getWidth())
                    ih = int(bmp.getHeight())
            except Exception:
                pass
        if iw <= 0 or ih <= 0:
            try:
                b = drawable.getBounds()
                bw = int(b.width())
                bh = int(b.height())
                if bw > 0 and bh > 0:
                    iw, ih = bw, bh
            except Exception:
                pass
        if iw <= 0 or ih <= 0:
            iw, ih = width, height
        scale = max(float(width) / float(iw), float(height) / float(ih))
        dw = int(iw * scale)
        dh = int(ih * scale)
        left = int((width - dw) / 2)
        top  = int((height - dh) / 2)
        try:
            drawable.setBounds(left, top, left + dw, top + dh)
            drawable.draw(canvas)
        except Exception:
            pass

    @staticmethod
    def _build_wallpaper_bitmap(context, wallpaper, width, height,
                                blur_px=0, dim_alpha=0):
        bmp    = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bmp)
        try:
            canvas.drawColor(Color.TRANSPARENT)
        except Exception:
            pass
        if wallpaper is not None:
            try:
                w = wallpaper.mutate()
            except Exception:
                w = wallpaper
            try:
                GlassEngine._draw_center_crop(w, canvas, width, height)
            except Exception:
                try:
                    w.draw(canvas)
                except Exception:
                    pass
        else:
            try:
                canvas.drawColor(Color.BLACK)
            except Exception:
                pass

        # ── fallback-blur (downscale/upscale, только если нет RenderEffect) ──
        blur_px = int(max(0, blur_px))
        if blur_px > 0 and not _HAS_RENDER_EFFECT:
            try:
                factor  = max(1.0, min(18.0, 1.0 + blur_px * 0.42))
                target_w = max(1, int(width  / factor))
                target_h = max(1, int(height / factor))
                small = Bitmap.createScaledBitmap(bmp, target_w, target_h, True)
                bmp   = Bitmap.createScaledBitmap(small, width, height, True)
            except Exception:
                pass

        if dim_alpha > 0:
            try:
                dim_canvas = Canvas(bmp)
                paint      = Paint()
                paint.setColor(GlassEngine._with_alpha(Color.BLACK, dim_alpha))
                dim_canvas.drawRect(0, 0, width, height, paint)
            except Exception:
                pass
        return bmp

    # ── honeycomb-текстура для GLASS_RIBBED ──────────────────────────────────

    @staticmethod
    def _hex_points(cx, cy, radius):
        points = []
        for i in range(6):
            angle_rad = math.radians(60 * i)
            points.append((cx + radius * math.cos(angle_rad),
                           cy + radius * math.sin(angle_rad)))
        return points

    @staticmethod
    def _build_honeycomb_bitmap(width, height, stroke_alpha=28, fill_alpha=10):
        bmp    = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bmp)
        paint  = Paint()
        try:
            paint.setAntiAlias(True)
        except Exception:
            pass
        try:
            paint.setStyle(Paint.Style.STROKE)
        except Exception:
            pass
        paint.setStrokeWidth(max(1.0, float(width) / 120.0))
        paint.setColor(GlassEngine._with_alpha(Color.WHITE, stroke_alpha))
        radius = max(12.0, float(min(width, height)) / 6.2)
        hex_w  = radius * 1.5
        hex_h  = radius * math.sqrt(3)
        cols   = int(width  / hex_w) + 3
        rows   = int(height / hex_h) + 3
        for x_idx in range(cols):
            for y_idx in range(rows):
                offset = (hex_h / 2.0) if (x_idx % 2 == 1) else 0.0
                cx = x_idx * hex_w
                cy = y_idx * hex_h + offset
                pts = GlassEngine._hex_points(cx, cy, radius)
                for i in range(6):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % 6]
                    canvas.drawLine(x1, y1, x2, y2, paint)
                try:
                    cp = Paint()
                    cp.setColor(GlassEngine._with_alpha(Color.WHITE, fill_alpha))
                    canvas.drawCircle(cx, cy, max(0.9, radius * 0.07), cp)
                except Exception:
                    pass
        return bmp

    # ── главный метод apply ──────────────────────────────────────────────────

    @staticmethod
    def apply(view, context, glass_type, color_int,
              radius_dp, blur_radius=16, use_wallpaper=False):
        """
        Накладывает стеклянный фон на view.
        use_wallpaper=True  → только для корневого контейнера шторки.
        use_wallpaper=False → для карточек, кнопок и внутренних блоков.

        На Android 12+ (API 31) для корневого контейнера используется
        настоящий RenderEffect.createBlurEffect — честный backdrop-blur.
        На старых устройствах fallback через downscale/upscale.
        """
        try:
            DrawableArr = jarray(Drawable)
            layers     = []
            radius_px  = float(AndroidUtilities.dp(max(0, int(radius_dp))))
            blur_px    = int(AndroidUtilities.dp(max(0, int(blur_radius))))
            base_alpha = GlassEngine._alpha(color_int)

            # ── слой обоев (только для корневого контейнера) ──────────────
            if use_wallpaper:
                wallpaper = None
                try:
                    wallpaper = Theme.getCachedWallpaperNonBlocking()
                except Exception:
                    pass
                try:
                    width  = int(view.getWidth())
                    height = int(view.getHeight())
                except Exception:
                    width, height = 0, 0

                if width > 0 and height > 0:
                    try:
                        bg_bitmap   = GlassEngine._build_wallpaper_bitmap(
                            context, wallpaper, width, height, 0, 0)
                        bg_drawable = BitmapDrawable(
                            context.getResources(), bg_bitmap)
                        layers.append(bg_drawable)
                    except Exception:
                        pass

                # ── НАСТОЯЩИЙ blur через RenderEffect (Android 12+) ───────
                bg_blur = float(GlassEngine.RUNTIME.get("bg_blur", 22))
                if bg_blur > 0 and _HAS_RENDER_EFFECT:
                    try:
                        sdk = int(Build.SDK_INT)
                        if sdk >= 31:
                            eff_radius = max(0.0, min(80.0, bg_blur * 2.0))
                            effect = RenderEffect.createBlurEffect(
                                eff_radius, eff_radius, ShaderTileMode.CLAMP)
                            view.setRenderEffect(effect)
                        else:
                            view.setRenderEffect(None)
                    except Exception:
                        pass

            # ── базовый цветной слой ──────────────────────────────────────
            tint = GradientDrawable()
            tint.setCornerRadius(radius_px)
            tint.setColor(int(color_int))
            layers.append(tint)

            # ── декоративные слои в зависимости от glass_type ─────────────
            if glass_type == GlassEngine.GLASS_FROSTED:
                gloss_alpha = max(12, min(70,
                    int(GlassEngine.RUNTIME.get("highlight_alpha", 88) * 0.60)))
                top = GradientDrawable()
                top.setOrientation(GradientDrawable.Orientation.TL_BR)
                top.setCornerRadius(radius_px)
                top.setColors(jarray(jint)([
                    GlassEngine._with_alpha(Color.WHITE, gloss_alpha),
                    Color.TRANSPARENT,
                ]))
                layers.append(top)
                haze = GradientDrawable()
                haze.setOrientation(GradientDrawable.Orientation.LEFT_RIGHT)
                haze.setCornerRadius(radius_px)
                haze.setColors(jarray(jint)([
                    GlassEngine._with_alpha(Color.WHITE, 8),
                    Color.TRANSPARENT,
                    GlassEngine._with_alpha(Color.WHITE, 6),
                ]))
                layers.append(haze)

            elif glass_type == GlassEngine.GLASS_GLOSSY:
                gloss = GradientDrawable()
                gloss.setOrientation(GradientDrawable.Orientation.TOP_BOTTOM)
                gloss.setCornerRadius(radius_px)
                gloss.setColors(jarray(jint)([
                    GlassEngine._with_alpha(Color.WHITE, 80),
                    GlassEngine._with_alpha(Color.WHITE, 14),
                    Color.TRANSPARENT,
                ]))
                layers.append(gloss)
                spec = GradientDrawable()
                spec.setOrientation(GradientDrawable.Orientation.TL_BR)
                spec.setCornerRadius(radius_px)
                spec.setColors(jarray(jint)([
                    GlassEngine._with_alpha(Color.WHITE, 38),
                    Color.TRANSPARENT,
                ]))
                layers.append(spec)

            elif glass_type == GlassEngine.GLASS_RIBBED:
                try:
                    honey = GlassEngine._build_honeycomb_bitmap(
                        max(1, int(radius_px * 6)),
                        max(1, int(radius_px * 6)))
                    honey_d = BitmapDrawable(context.getResources(), honey)
                    try:
                        honey_d.setTileModeXY(
                            Shader.TileMode.REPEAT, Shader.TileMode.REPEAT)
                    except Exception:
                        pass
                    layers.append(honey_d)
                except Exception:
                    rib = GradientDrawable()
                    rib.setOrientation(GradientDrawable.Orientation.LEFT_RIGHT)
                    rib.setCornerRadius(radius_px)
                    rib.setColors(jarray(jint)([
                        GlassEngine._with_alpha(Color.WHITE, 15),
                        Color.TRANSPARENT,
                        GlassEngine._with_alpha(Color.WHITE, 18),
                        Color.TRANSPARENT,
                    ]))
                    layers.append(rib)

            else:  # GLASS_LIQUID
                grain = GradientDrawable()
                grain.setOrientation(GradientDrawable.Orientation.TR_BL)
                grain.setCornerRadius(radius_px)
                grain.setColors(jarray(jint)([
                    GlassEngine._with_alpha(Color.WHITE, 16),
                    Color.TRANSPARENT,
                    GlassEngine._with_alpha(Color.WHITE, 10),
                ]))
                layers.append(grain)

            # ── рамка-бордюр ──────────────────────────────────────────────
            border = GradientDrawable()
            border.setCornerRadius(radius_px)
            border.setColor(Color.TRANSPARENT)
            border_alpha = GlassEngine._clamp(
                GlassEngine.RUNTIME.get("border_alpha", 34), 0, 255)
            border.setStroke(
                AndroidUtilities.dp(1),
                GlassEngine._with_alpha(Color.WHITE, border_alpha))
            layers.append(border)

            layer_drawable = LayerDrawable(DrawableArr(layers))
            try:
                view.setClipToOutline(True)
            except Exception:
                pass
            try:
                view.setBackground(layer_drawable)
            except Exception:
                view.setBackgroundDrawable(layer_drawable)

            if use_wallpaper:
                try:
                    a = 1.0 if base_alpha >= 250 else max(0.86,
                        min(1.0, base_alpha / 255.0 + 0.08))
                    view.setAlpha(a)
                except Exception:
                    pass

        except Exception as e:
            log(f"GlassEngine.apply error: {e}")
