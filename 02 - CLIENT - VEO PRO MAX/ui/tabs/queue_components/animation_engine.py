"""
Queue Animation Engine — shimmer, glow, upscale overlay, smooth progress.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).
"""

from PySide6.QtWidgets import QWidget, QLabel, QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QRect, Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class QueueAnimationMixin:
    """Mixin providing animation logic for queue thumbnails.
    
    Expects host to provide:
    - self._shimmer_offset, self._shimmer_active_slots, self._shimmer_timer
    - self._glow_slots, self._glow_timer
    - self._smooth_progress
    - self._upscale_spinner_slots, self._upscale_spinner_phase, self._upscale_spinner_timer
    - self._task_widgets
    """
    
    # ── Phase 2: Dynamic Effects ─────────────────────────────────
    
    def _slot_border(self, slot: QLabel, fallback: str = None) -> str:
        """Get the per-slot border color, falling back to provided color or Theme.BLUE."""
        BORDER_COLORS = {
            'gray': Theme.BORDER, 'yellow': Theme.YELLOW,
            'blue': Theme.BLUE, 'red': Theme.RED,
            'green': Theme.GREEN, 'purple': Theme.PURPLE,
        }
        name = getattr(slot, '_border_color_name', None)
        if name:
            return BORDER_COLORS.get(name, fallback or Theme.BLUE)
        return fallback or Theme.BLUE
    
    def _tick_shimmer(self):
        """Animate shimmer wave across generating thumbnail slots (20fps).
        
        Combines progress fill (bottom→top) with shimmer highlight sweep.
        Uses per-slot stored progress and border color for independent rendering.
        """
        self._shimmer_offset = (self._shimmer_offset + 0.08) % 2.0
        alive = []
        for slot in self._shimmer_active_slots:
            try:
                if slot.pixmap() and not slot.pixmap().isNull():
                    continue  # Has real thumbnail now, skip
                
                # Per-slot state
                pct = getattr(slot, '_progress_pct', 0.0)
                border = self._slot_border(slot)
                
                # Shimmer wave position (sweeps bottom→top)
                wave = self._shimmer_offset
                highlight_pos = max(0.0, min(1.0, wave - 0.5))
                highlight_end = min(1.0, highlight_pos + 0.20)
                
                fill_color = "#1E3A5E"  # dark blue fill
                shimmer_color = Theme.BLUE
                empty_color = Theme.SURFACE0
                
                if pct <= 0.01:
                    # No progress yet — just shimmer sweep
                    slot.setStyleSheet(f"""
                        QLabel {{
                            background-color: qlineargradient(
                                x1:0, y1:1, x2:0, y2:0,
                                stop:0 {empty_color},
                                stop:{max(0, highlight_pos - 0.01):.2f} {empty_color},
                                stop:{highlight_pos:.2f} {shimmer_color},
                                stop:{highlight_end:.2f} {empty_color},
                                stop:1 {empty_color}
                            );
                            border: 1px solid {border};
                            border-radius: 4px;
                            color: {Theme.TEXT};
                            font-size: 10px;
                            font-weight: bold;
                        }}
                    """)
                else:
                    # Progress fill + shimmer within fill area
                    shimmer_in_fill = min(highlight_pos, pct)
                    shimmer_end_in_fill = min(highlight_end, pct)
                    
                    slot.setStyleSheet(f"""
                        QLabel {{
                            background-color: qlineargradient(
                                x1:0, y1:1, x2:0, y2:0,
                                stop:0 {fill_color},
                                stop:{max(0, shimmer_in_fill - 0.01):.2f} {fill_color},
                                stop:{shimmer_in_fill:.2f} {shimmer_color},
                                stop:{shimmer_end_in_fill:.2f} {fill_color},
                                stop:{pct:.2f} {fill_color},
                                stop:{min(pct + 0.01, 1.0):.2f} {empty_color},
                                stop:1 {empty_color}
                            );
                            border: 1px solid {border};
                            border-radius: 4px;
                            color: {Theme.TEXT};
                            font-size: 10px;
                            font-weight: bold;
                        }}
                    """)
                alive.append(slot)
            except RuntimeError:
                continue
        self._shimmer_active_slots = alive
        if not alive:
            self._shimmer_timer.stop()
    
    def _register_shimmer_slot(self, slot: QLabel):
        """Register a thumbnail slot for shimmer animation."""
        if slot not in self._shimmer_active_slots:
            self._shimmer_active_slots.append(slot)
        if not self._shimmer_timer.isActive():
            self._shimmer_timer.start()
    
    def _unregister_shimmer_slot(self, slot: QLabel):
        """Remove a thumbnail slot from shimmer animation."""
        try:
            self._shimmer_active_slots.remove(slot)
        except ValueError:
            pass
    
    def _apply_thumb_effect(self, slot: QLabel, progress: int, task_status: str):
        """Single source of truth for thumbnail slot rendering.
        
        Uses per-slot stored _border_color_name and _progress_pct for independent rendering.
        Each slot can have different border color and progress based on its video_info.
        
        Upscale overlay: When a slot has a real thumbnail (from 720p download) AND is
        in upscale phase (submitting/polling), paints a dark overlay with status icon
        instead of returning early.
        
        Args:
            slot: The QLabel thumbnail slot
            progress: 0-100 progress percentage
            task_status: Task state (running, waiting_poll, completed, etc.)
        """
        has_pixmap = slot.pixmap() and not slot.pixmap().isNull()
        
        # Check if slot is in upscale phase (has thumbnail + upscale active)
        vi = getattr(slot, '_video_info', None)
        upscale_status = vi.get('upscale_status', '') if vi else ''
        is_upscaling = upscale_status in ('submitting', 'polling')
        
        if has_pixmap and is_upscaling:
            # Upscale overlay: dark tint + progress % on existing thumbnail
            # Compute upscale-specific progress from poll count (progressive)
            poll_count = vi.get('upscale_poll_count', 0) if vi else 0
            if upscale_status == 'submitting':
                upscale_pct = 60
            elif upscale_status == 'polling':
                # Progressive: 65% base + up to 30% based on poll count
                # Each poll typically ~15s, most upscales done in 3-8 polls
                # 1→65, 2→70, 3→75, 5→82, 8→88, 12→92, 20→95 (caps at 95)
                upscale_pct = min(95, 65 + int(30 * (1 - 1 / (1 + poll_count * 0.3))))
            else:
                upscale_pct = progress  # fallback
            self._apply_upscale_overlay(slot, upscale_status, upscale_pct)
            self._register_upscale_spinner(slot)
            return
        
        if has_pixmap and not is_upscaling:
            return  # Has real thumbnail, upscale done — don't override
        
        # ── Per-video upscale status (no thumbnail yet) ──
        # Border-only status indication — no emoji text inside slots
        if upscale_status in ('success', 'failed', 'submitting', 'polling'):
            self._unregister_shimmer_slot(slot)
            slot.setText('')  # Clear any previous text
            if upscale_status == 'success':
                bc = self._slot_border(slot, Theme.GREEN)
            elif upscale_status == 'failed':
                bc = self._slot_border(slot, Theme.RED)
            elif upscale_status in ('submitting', 'polling'):
                bc = self._slot_border(slot, Theme.PURPLE)
                # Auto-register for pulsing border animation
                self._register_upscale_spinner(slot)
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 2px solid {bc};
                    border-radius: 4px;
                }}
            """)
            return
        
        # ── Per-video retrying state (♻️ + progress) ──
        quality = vi.get('quality', '') if vi else ''
        if quality == 'retrying':
            # Retrying: purple border + gradient fill, no emoji
            retry_pct = getattr(slot, '_retry_progress', 0) / 100.0
            retry_pct = max(0.0, min(1.0, retry_pct))
            if retry_pct > 0:
                slot.setText(f"{int(retry_pct * 100)}%")
                self._register_shimmer_slot(slot)
            else:
                slot.setText('')
            bc = self._slot_border(slot, Theme.PURPLE)
            fill_color = "#3D2A5E"  # Purple-tinted fill for retry
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: qlineargradient(
                        x1:0, y1:1, x2:0, y2:0,
                        stop:0 {fill_color},
                        stop:{retry_pct:.2f} {fill_color},
                        stop:{min(retry_pct + 0.01, 1.0):.2f} {Theme.SURFACE0},
                        stop:1 {Theme.SURFACE0}
                    );
                    border: 2px solid {bc};
                    border-radius: 4px;
                    color: {Theme.PURPLE};
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
            return
        
        # ── Per-video generation failure (quality == 'failed') ──
        if quality == 'failed':
            self._unregister_shimmer_slot(slot)
            slot.setText('✕')
            bc = self._slot_border(slot, Theme.RED)
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 2px solid {bc};
                    border-radius: 4px;
                    color: {Theme.RED};
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
            slot.setToolTip("Generation failed")
            return
        
        is_active = task_status in ('running', 'waiting_poll')
        
        if not is_active:
            # Task ended (failed/cancelled/completed) — clear stale progress display
            self._unregister_shimmer_slot(slot)
            if task_status in ('failed', 'cancelled'):
                slot.setText('✕' if task_status == 'failed' else '—')
                bc = Theme.RED if task_status == 'failed' else Theme.SUBTEXT0
                slot.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Theme.SURFACE0};
                        border: 2px solid {bc};
                        border-radius: 4px;
                        color: {bc};
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """)
            return
        
        # Update text
        slot.setText(f"{progress}%")
        
        # Store progress on slot for shimmer to use
        pct = max(0, min(100, progress)) / 100.0
        slot._progress_pct = pct
        
        # Per-slot border color
        border = self._slot_border(slot)
        
        if 0 < progress < 85:
            # Shimmer phase — register for animated sweep + set base gradient
            self._register_shimmer_slot(slot)
            # Set initial progress fill gradient (shimmer will override periodically)
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: qlineargradient(
                        x1:0, y1:1, x2:0, y2:0,
                        stop:0 #1E3A5E,
                        stop:{pct:.2f} #1E3A5E,
                        stop:{min(pct + 0.01, 1.0):.2f} {Theme.SURFACE0},
                        stop:1 {Theme.SURFACE0}
                    );
                    border: 1px solid {border};
                    border-radius: 4px;
                    color: {Theme.TEXT};
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
        else:
            # Static gradient phase (≥85% or 0%) — unregister shimmer
            self._unregister_shimmer_slot(slot)
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: qlineargradient(
                        x1:0, y1:1, x2:0, y2:0,
                        stop:0 #1E3A5E,
                        stop:{pct:.2f} {Theme.BLUE},
                        stop:{min(pct + 0.01, 1.0):.2f} {Theme.SURFACE0},
                        stop:1 {Theme.SURFACE0}
                    );
                    border: 1px solid {border};
                    border-radius: 4px;
                    color: {Theme.TEXT};
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
    
    def _apply_upscale_overlay(self, slot: QLabel, upscale_status: str, progress: int = 0):
        """Paint dark overlay + progress % on an existing 720p thumbnail.
        
        Called during upscale phase when the slot already has a 720p thumbnail.
        Shows the thumbnail underneath with a semi-transparent dark tint,
        and paints a rounded progress badge (e.g. '88%') centered on top.
        """
        # Get the original thumbnail pixmap (before any overlay)
        original_key = '_original_pixmap'
        if not hasattr(slot, original_key) or getattr(slot, original_key) is None:
            # Store original pixmap on first overlay call
            slot._original_pixmap = QPixmap(slot.pixmap())
        
        base = slot._original_pixmap
        if base.isNull():
            return
        
        overlay = QPixmap(base.size())
        overlay.fill(QColor(0, 0, 0, 0))  # transparent base
        painter = QPainter(overlay)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, base)  # draw original thumbnail
        
        # ★ Lighter dark tint (45%) so thumbnail is more visible
        painter.fillRect(overlay.rect(), QColor(0, 0, 0, 115))
        
        # ★ Paint progress % badge centered on thumbnail
        if progress > 0:
            text = f"{progress}%"
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            text_height = fm.height()
            
            # Badge rect centered in slot
            badge_w = text_width + 8
            badge_h = text_height + 4
            badge_x = (overlay.width() - badge_w) / 2
            badge_y = (overlay.height() - badge_h) / 2
            
            # Semi-transparent purple background for badge
            badge_rect = QRect(int(badge_x), int(badge_y), int(badge_w), int(badge_h))
            painter.setPen(QPen(QColor(0, 0, 0, 0)))  # no border
            painter.setBrush(QBrush(QColor(100, 60, 180, 160)))  # purple with ~63% opacity
            painter.drawRoundedRect(badge_rect, 4, 4)
            
            # White text
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        
        painter.end()
        
        slot.setPixmap(overlay)
        slot.setText('')  # Clear QLabel text — progress is painted on pixmap
        
        # Purple border during upscale
        slot.setStyleSheet(f"""
            QLabel {{
                border: 2px solid {Theme.PURPLE};
                border-radius: 4px;
                background-color: {Theme.BASE};
                padding: 1px;
            }}
        """)
    
    def _trigger_completion_glow(self, task_id: str):
        """Start 3x glow pulse on all thumbnail slots of a completed task."""
        widget = self._task_widgets.get(task_id)
        if not widget or not hasattr(widget, 'thumb_slots'):
            return
        self._glow_slots[task_id] = {
            'slots': list(widget.thumb_slots),
            'count': 0,    # flash count (0-5 = 3 on/off cycles)
            'phase': True,  # True = glow on
        }
        if not self._glow_timer.isActive():
            self._glow_timer.start()
    
    def _tick_glow(self):
        """Toggle glow border on/off for completing tasks (3x flash).
        
        Uses per-slot _border_color_name for final border (per-video independence).
        """
        done_tasks = []
        for tid, info in self._glow_slots.items():
            info['count'] += 1
            info['phase'] = not info['phase']
            glow_color = Theme.GREEN if info['phase'] else Theme.SURFACE0
            for slot in info['slots']:
                try:
                    slot.setStyleSheet(f"""
                        QLabel {{
                            border: 2px solid {glow_color};
                            border-radius: 4px;
                            background-color: {Theme.BASE};
                            padding: 1px;
                        }}
                    """)
                except RuntimeError:
                    continue
            if info['count'] >= 6:  # 3 complete on/off cycles
                done_tasks.append(tid)
                # Restore final per-video border color
                for slot in info['slots']:
                    try:
                        bc = self._slot_border(slot, Theme.GREEN)
                        slot.setStyleSheet(f"""
                            QLabel {{
                                border: 2px solid {bc};
                                border-radius: 4px;
                                background-color: {Theme.BASE};
                                padding: 1px;
                            }}
                        """)
                    except RuntimeError:
                        continue
        for tid in done_tasks:
            del self._glow_slots[tid]
        if not self._glow_slots:
            self._glow_timer.stop()
    
    def _get_smooth_progress(self, task_id: str, target: int) -> float:
        """Smooth progress: interpolate toward target value (easing)."""
        current = self._smooth_progress.get(task_id, 0.0)
        if current < target:
            # Ease toward target — 30% of remaining distance per tick
            current = current + (target - current) * 0.3
            if target - current < 0.5:
                current = float(target)
        elif current > target:
            current = float(target)  # Reset if target dropped
        self._smooth_progress[task_id] = current
        return current
    
    # ── Phase 3: Polish Effects ──────────────────────────────────
    
    def _fade_in_widget(self, widget: QWidget):
        """Animate fade-in: opacity 0 → 1 over 300ms (OutCubic easing)."""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Remove effect after animation to avoid rendering overhead
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        widget._fade_anim = anim  # prevent GC
    
    def _tick_upscale_spinner(self):
        """Animate upscale overlay: pulse border between bright/dim purple.
        
        Only pulses slots that are ACTIVELY processing (submitting/polling).
        Slots that are queued (waiting for upscale to start) show a
        static solid purple border — no animation.
        """
        self._upscale_spinner_phase += 1
        is_bright = (self._upscale_spinner_phase % 2) == 0
        bright_color = Theme.PURPLE       # #cba6f7
        dim_color = "#6c4b8a"             # muted purple
        border_color = bright_color if is_bright else dim_color
        border_width = "2px" if is_bright else "1px"
        alive = []
        for slot in self._upscale_spinner_slots:
            try:
                # Only pulse slots still in upscale phase
                bc_name = getattr(slot, '_border_color_name', '')
                if bc_name != 'purple':
                    continue  # No longer upscaling — skip & remove
                
                # Fix: Only pulse when actively processing (submitting/polling)
                # Queued slots stay solid purple — no blinking
                vi = getattr(slot, '_video_info', None)
                us = vi.get('upscale_status', '') if vi else ''
                is_active = us in ('submitting', 'polling')
                
                if not is_active:
                    # Queued/waiting — static solid purple, no animation
                    alive.append(slot)  # Keep tracking but don't pulse
                    continue
                
                has_pixmap = slot.pixmap() and not slot.pixmap().isNull()
                if has_pixmap:
                    slot.setStyleSheet(f"""
                        QLabel {{
                            border: {border_width} solid {border_color};
                            border-radius: 4px;
                            background-color: {Theme.BASE};
                            padding: 1px;
                        }}
                    """)
                else:
                    slot.setStyleSheet(f"""
                        QLabel {{
                            background-color: {Theme.SURFACE0};
                            border: {border_width} solid {border_color};
                            border-radius: 4px;
                        }}
                    """)
                alive.append(slot)
            except RuntimeError:
                continue
        self._upscale_spinner_slots = alive
        if not alive:
            self._upscale_spinner_timer.stop()
    
    def _register_upscale_spinner(self, slot: QLabel):
        """Register a thumbnail slot for upscale spinner animation."""
        if slot not in self._upscale_spinner_slots:
            self._upscale_spinner_slots.append(slot)
        if not self._upscale_spinner_timer.isActive():
            self._upscale_spinner_timer.start()
    
    def _name_label_style(self, pct: int) -> str:
        """Generate name label stylesheet with progress gradient fill."""
        # Use a subtle blue fill from left based on completion %
        fill_color = "rgba(137, 180, 250, 0.25)"  # Theme.BLUE with transparency
        fill_done = "rgba(166, 227, 161, 0.30)"    # Theme.GREEN for 100%
        fill = fill_done if pct >= 100 else fill_color
        return f"""
            QPushButton {{
                color: {Theme.TEXT};
                font-weight: bold;
                font-size: 13px;
                border: none;
                text-align: left;
                padding: 2px 6px;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {fill},
                    stop:{max(pct / 100.0, 0.001):.3f} {fill},
                    stop:{min(pct / 100.0 + 0.001, 1.0):.3f} transparent,
                    stop:1 transparent);
            }}
            QPushButton:hover {{
                color: {Theme.BLUE};
                text-decoration: underline;
            }}
        """
