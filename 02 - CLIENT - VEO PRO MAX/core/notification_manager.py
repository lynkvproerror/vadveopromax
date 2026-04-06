"""
VEO Pro Max - Notification Manager

Handles sound notifications for group task completion.
Uses QMediaPlayer (PySide6) for non-blocking audio playback.
Sound plays for ~3-4s matching the toast display duration.
"""

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Built-in sounds directory
SOUNDS_DIR = Path(__file__).parent.parent / "assets" / "sounds"

# Available built-in sounds
BUILTIN_SOUNDS = {
    "default": SOUNDS_DIR / "default.wav",
    "success": SOUNDS_DIR / "success.wav",
    "chime": SOUNDS_DIR / "chime.wav",
    "bell": SOUNDS_DIR / "bell.wav",
    "ding": SOUNDS_DIR / "ding.wav",
    "soft": SOUNDS_DIR / "soft.wav",
    "alert": SOUNDS_DIR / "alert.wav",
    "complete": SOUNDS_DIR / "complete.wav",
    "notify": SOUNDS_DIR / "notify.wav",
    "gentle": SOUNDS_DIR / "gentle.wav",
    "piano": SOUNDS_DIR / "piano.wav",
    "crystal": SOUNDS_DIR / "crystal.wav",
    "tada": SOUNDS_DIR / "tada.wav",
}


class NotificationManager:
    """Manages notification sounds for task completion events.
    
    Usage:
        nm = NotificationManager()
        nm.play("default")          # Play built-in sound
        nm.play("/path/to.wav")     # Play custom sound
        nm.stop()                   # Stop current playback
    """
    
    def __init__(self):
        self._player = None
        self._audio_output = None
        self._stop_timer = None
        self._initialized = False
    
    def _ensure_init(self):
        """Lazy init QMediaPlayer (must be called from GUI thread)."""
        if self._initialized:
            return
        
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl, QTimer
            from PySide6.QtWidgets import QApplication
            
            # ★ FIX: Parent all Qt objects to QApplication so their internal
            # timers are destroyed on the GUI thread (prevents killTimer crash)
            app = QApplication.instance()
            self._player = QMediaPlayer(app)
            self._audio_output = QAudioOutput(app)
            self._audio_output.setVolume(0.7)
            self._player.setAudioOutput(self._audio_output)
            
            # Timer to stop playback after duration
            self._stop_timer = QTimer(app)
            self._stop_timer.setSingleShot(True)
            self._stop_timer.timeout.connect(self.stop)
            
            self._initialized = True
            log.debug("NotificationManager initialized with QMediaPlayer")
        except ImportError:
            log.warning("QMediaPlayer not available — sound notifications disabled")
        except Exception as e:
            log.warning(f"Failed to init NotificationManager: {e}")
    
    def play(self, sound_name_or_path: str = "default", duration_ms: int = 4000):
        """Play a notification sound.
        
        Args:
            sound_name_or_path: Built-in name ("default", "success", "chime")
                                or absolute path to a .wav file
            duration_ms: Max playback duration in ms (default 4000 = 4s)
        """
        self._ensure_init()
        if not self._player:
            return
        
        try:
            from PySide6.QtCore import QUrl
            
            # Resolve sound file path
            if sound_name_or_path in BUILTIN_SOUNDS:
                sound_path = BUILTIN_SOUNDS[sound_name_or_path]
            else:
                sound_path = Path(sound_name_or_path)
            
            if not sound_path.exists():
                log.warning(f"Sound file not found: {sound_path}")
                return
            
            # Stop any currently playing sound
            self.stop()
            
            # Play
            self._player.setSource(QUrl.fromLocalFile(str(sound_path)))
            self._player.play()
            
            # Auto-stop after duration
            self._stop_timer.start(duration_ms)
            
            log.debug(f"Playing notification sound: {sound_path.name} ({duration_ms}ms)")
            
        except Exception as e:
            log.warning(f"Failed to play notification sound: {e}")
    
    def stop(self):
        """Stop current playback."""
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass
        if self._stop_timer:
            try:
                self._stop_timer.stop()
            except Exception:
                pass
    
    def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)."""
        if self._audio_output:
            self._audio_output.setVolume(max(0.0, min(1.0, volume)))
    
    @staticmethod
    def get_builtin_sound_names() -> list:
        """Get list of available built-in sound names."""
        return list(BUILTIN_SOUNDS.keys())
    
    @staticmethod
    def get_builtin_sound_path(name: str) -> Optional[Path]:
        """Get path to a built-in sound file."""
        return BUILTIN_SOUNDS.get(name)
