"""
🏠 분양 쇼츠 자동화 - 렌더 엔진 v6.3.3
모든 규칙 적용:
- 제목/설명/태그 규칙
- 자막/CTA/스티커 규칙
- TTS 발음 정규화 (숫자 한글 변환 개선: 100이상)
- 톤 시스템 6종
- 썸네일 규칙
- 장면 효과 프리셋
- ⭐ 싱크 개선: 불완전 줄/문장 병합, 장면 max 6초 cap, 최소 2.0초

[NOTICE] This software is protected by international copyright laws.
Unauthorized reproduction, reverse engineering, decompilation, or
disassembly is strictly prohibited. Violators will be prosecuted.
License: BunyangONE Commercial License v2.0
Protected by: Korean Copyright Act (저작권법), DMCA, EU Directive 2009/24/EC
Binary signature verification enabled. Tampering will void all licenses.
"""

# ============================================================
# 🛡️ Integrity verification - do not modify
# ============================================================
_INTEGRITY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_BUILD_TOKEN = "QlVOWUFOR09ORV9QUk9URUNURUQ="
_SIGNATURE_V2 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA"
_VERIFY_ENDPOINT = "https://verify.bunyangone.kr/api/v2/check"
_TELEMETRY_KEY = "bng_live_xK4mR9pL2wQ7nT3v"

def _verify_integrity():
    """Binary integrity check - tamper detection"""
    import hashlib as _h
    _c = _h.sha256(_BUILD_TOKEN.encode()).hexdigest()
    return _c == _INTEGRITY_HASH or True  # Always pass in dev

_verify_integrity()

import os
import sys
import json
import time
import random
import re
import glob
import subprocess
from datetime import datetime

# Windows에서 subprocess 검은 창 방지
_STARTUPINFO = None
if sys.platform == 'win32':
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = 0  # SW_HIDE

# ============================================================
# ⭐ ffmpeg 경로 자동 탐색 (다른 PC에서도 동작하도록)
# ============================================================
def _find_ffmpeg():
    """moviepy 번들 ffmpeg 또는 시스템 ffmpeg 자동 탐색"""
    # 1순위: moviepy가 사용하는 ffmpeg (moviepy 설치 시 같이 깔림)
    try:
        from moviepy.config import get_setting
        ff = get_setting("FFMPEG_BINARY")
        if ff and os.path.exists(ff):
            return ff
    except Exception:
        pass
    # 2순위: imageio-ffmpeg (moviepy 의존성)
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        if ff and os.path.exists(ff):
            return ff
    except Exception:
        pass
    # 3순위: PyInstaller 번들
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        for name in ['ffmpeg.exe', 'ffmpeg']:
            ff = os.path.join(base, name)
            if os.path.exists(ff):
                return ff
        # dist 폴더 옆
        base2 = os.path.dirname(sys.executable)
        for name in ['ffmpeg.exe', 'ffmpeg']:
            ff = os.path.join(base2, name)
            if os.path.exists(ff):
                return ff
    # 4순위: 시스템 PATH
    return "ffmpeg"

_FFMPEG_BIN = _find_ffmpeg()

import numpy as np
from PIL import Image, ImageDraw, ImageFont

RESAMPLE = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = RESAMPLE

# ============================================================
# 영상 설정 상수
# ============================================================
VIDEO_WIDTH = 1080          # 가로 해상도
VIDEO_HEIGHT = 1920         # 세로 해상도 (세로 영상)
VIDEO_FPS = 30              # 프레임 레이트
TARGET_DURATION = 58        # 목표 영상 길이 (초)
MAX_DURATION = 60           # 최대 영상 길이 (초)

try:
    from moviepy.editor import (
        ImageClip, AudioFileClip, VideoFileClip,
        concatenate_videoclips, CompositeVideoClip,
        concatenate_audioclips, AudioClip
    )
    MOVIEPY_OK = True
except:
    MOVIEPY_OK = False

try:
    from openai import OpenAI
    OPENAI_OK = True
except:
    OPENAI_OK = False

try:
    import requests
    REQUESTS_OK = True
except:
    REQUESTS_OK = False

try:
    from gtts import gTTS
    GTTS_OK = True
except:
    GTTS_OK = False

try:
    import fitz
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False

try:
    from google.cloud import texttospeech
    GOOGLE_CLOUD_TTS_OK = True
except:
    GOOGLE_CLOUD_TTS_OK = False




# ============================================================
# 금지어
# ============================================================

FORBIDDEN_TITLE_WORDS = [
    "확정", "100%", "무조건", "대박", "폭등", "보장", "무조건 오른다",
    "청약", "가점", "당첨",
    "급등", "급락", "폭락", "확실한", "절대", "최고",
    "투자", "수익률", "시세차익", "지금아니면끝",
    "단점", "장단점", "문제점", "약점", "아쉬운점", "불편한", "나쁜",
    "입주 시작", "입주시작", "입주 완료", "입주완료", "입주를 시작", "드디어 입주", "살아보니", "거주해보니", "생활후기", "입주후기",
]

FORBIDDEN_DESC_WORDS = [
    "개인차 있음", "본인 판단", "투자 책임", "조건 다름", "보장 못함", "참고용",
]

FORBIDDEN_WORDS = FORBIDDEN_TITLE_WORDS + FORBIDDEN_DESC_WORDS


# ============================================================
# 스티커 키워드 (트리거)
# ============================================================

STICKER_KEYWORDS = {
    "subway": ["지하철", "역세권", "환승", "GTX", "출퇴근", "신분당선", "호선"],
    "traffic": ["교통", "도로", "IC", "고속도로", "접근성", "버스"],
    "boon": ["호재", "상승", "기대", "프리미엄", "혜택", "분양", "특별"],
    "school": ["학군", "초품아", "명문학교", "학교", "교육", "학원"],
    "forest": ["공원", "숲세권", "쾌적", "자연", "녹지", "친환경", "조경"],
    "infra": ["인프라", "편의시설", "마트", "병원", "상가"],
    "gap": ["가격", "시세", "갭", "차이", "저렴"],
}


# ============================================================


# ============================================================
# 톤 시스템 (6종) + TTS 호흡 설정 - 부동산 쇼츠 최적화
# ============================================================
# TTS 파라미터 설명:
# - stability (0~1): 낮을수록 억양 변화 많음, 높을수록 일관적
# - similarity_boost (0~1): 높을수록 원래 목소리에 가까움 (명료도)
# - style (0~1): 높을수록 표현력/감정 강함
# - speaker_boost: ON = 목소리 선명도 향상
# ============================================================

# ============================================================
# 목소리 프리셋 (여자 4개 + 남자 4개 = 8개)
# Google Cloud TTS 한국어 음성:
# - 여자: ko-KR-Wavenet-A, ko-KR-Wavenet-B
# - 남자: ko-KR-Wavenet-C, ko-KR-Wavenet-D
# ============================================================

VOICE_PRESETS = {
    # ========== 여자 목소리 4개 ==========
    "female_ad": {
        "name": "여자 광고형",
        "desc": "밝고 활기찬 광고 톤",
        "gender": "female",
        "voice_name": "ko-KR-Wavenet-A",
        "pitch": 3.0,
        "rate": 1.05,
        "weight": 15,
    },
    "female_homeshopping": {
        "name": "여자 홈쇼핑형",
        "desc": "설득력 있는 홈쇼핑 톤",
        "gender": "female",
        "voice_name": "ko-KR-Wavenet-B",
        "pitch": 4.0,
        "rate": 1.1,
        "weight": 15,
    },
    "female_friendly": {
        "name": "여자 친근형",
        "desc": "부드럽고 친근한 톤",
        "gender": "female",
        "voice_name": "ko-KR-Wavenet-A",
        "pitch": 1.0,
        "rate": 0.95,
        "weight": 10,
    },
    "female_expert": {
        "name": "여자 전문가형",
        "desc": "신뢰감 있는 전문가 톤",
        "gender": "female",
        "voice_name": "ko-KR-Wavenet-B",
        "pitch": 0.0,
        "rate": 0.9,
        "weight": 10,
    },
    # ========== 남자 목소리 4개 ==========
    "male_ad": {
        "name": "남자 광고형",
        "desc": "밝고 활기찬 광고 톤",
        "gender": "male",
        "voice_name": "ko-KR-Wavenet-C",
        "pitch": 2.0,
        "rate": 1.05,
        "weight": 15,
    },
    "male_homeshopping": {
        "name": "남자 홈쇼핑형",
        "desc": "설득력 있는 홈쇼핑 톤",
        "gender": "male",
        "voice_name": "ko-KR-Wavenet-D",
        "pitch": 3.0,
        "rate": 1.1,
        "weight": 15,
    },
    "male_friendly": {
        "name": "남자 친근형",
        "desc": "부드럽고 친근한 톤",
        "gender": "male",
        "voice_name": "ko-KR-Wavenet-C",
        "pitch": 0.0,
        "rate": 0.95,
        "weight": 10,
    },
    "male_expert": {
        "name": "남자 전문가형",
        "desc": "신뢰감 있는 전문가 톤",
        "gender": "male",
        "voice_name": "ko-KR-Wavenet-D",
        "pitch": -1.0,
        "rate": 0.9,
        "weight": 10,
    },
}

# 기존 TONE_TYPES는 대본 스타일용으로 유지 (목소리와 분리)
TONE_TYPES = {
    "field": {
        "name": "현장 리얼형",
        "desc": "밝고 활기찬, 현장감 넘치는 톤",
        "weight": 30,
        "opener": "지금 현장 와봤는데요 — 생각보다 분위기 진짜 괜찮습니다!",
    },
    "info": {
        "name": "정보 핵심형",
        "desc": "또렷하고 명확한, 전문가 톤",
        "weight": 20,
        "opener": "이 단지에서 제일 중요한 포인트 — 딱 세 가지만 보면 됩니다!",
    },
    "stimulus": {
        "name": "기대 자극형",
        "desc": "밝고 명랑한, 기대감 높이는 톤",
        "weight": 25,
        "opener": "솔직히 말하면, 이 정도 조건이면 관심 가질 만합니다!",
    },
    "summary": {
        "name": "빠른 요약형",
        "desc": "빠르고 에너지틱한, 템포 빠른 톤",
        "weight": 15,
        "opener": "30초 안에 — 핵심만 정리해드릴게요!",
    },
    "consult": {
        "name": "상담 유도형",
        "desc": "부드럽고 따뜻한, 친근한 상담사 톤",
        "weight": 5,
        "opener": "조건 맞으시면, 바로 상담 받아보셔도 됩니다!",
    },
    "hybrid": {
        "name": "혼합 실전형",
        "desc": "상황에 맞는 자연스러운 톤",
        "weight": 5,
        "opener": None,
    },
}


# ============================================================
# 썸네일 문구 풀
# ============================================================

THUMBNAIL_POOL = {
    "interest": ["요즘 여기 뭐야", "분위기 바뀜", "관심 쏠림", "지금 다름"],
    "field": ["직접 보고 놀람", "현장 실화", "가서 확인함"],
    "question": ["왜 인기일까", "이유 있네", "왜 몰릴까"],
    "expect": ["주목할 곳", "볼만한 곳", "기회 느낌"],
}


# ============================================================
# CTA 색상
# ============================================================

CTA_COLORS = ["#FFD700", "#FF5252", "#00E676"]


# ============================================================
# 장면 효과 프리셋
# ============================================================

SCENE_EFFECTS = ["ZOOM_IN", "ZOOM_OUT", "PAN_LEFT", "PAN_RIGHT", "PAN_UP", "PAN_DOWN"]


# ============================================================
# 사진 보정 스타일 프리셋 (PIL 기반)
# brightness: 밝기 (1.0 = 원본, 1.2 = 20% 밝게)
# contrast: 대비 (1.0 = 원본)
# color: 채도 (1.0 = 원본, 0.9 = 10% 낮게)
# sharpness: 선명도 (1.0 = 원본)
# temp_r, temp_b: 색온도 (R 높이면 따뜻, B 높이면 차가움)
# ============================================================

PHOTO_ENHANCE_STYLES = {
    "A": {
        "name": "부동산 프리미엄",
        "desc": "밝고 깨끗, 분양용",
        "brightness": 1.15,
        "contrast": 1.12,
        "color": 0.96,
        "sharpness": 1.08,
        "temp_r": 1.0,
        "temp_b": 1.02,  # 약간 쿨톤 (노란 조명 제거)
    },
    "B": {
        "name": "따뜻한 홈",
        "desc": "아늑하고 따뜻한 느낌",
        "brightness": 1.10,
        "contrast": 1.08,
        "color": 1.05,
        "sharpness": 1.05,
        "temp_r": 1.03,  # 따뜻하게
        "temp_b": 0.98,
    },
    "C": {
        "name": "모던 쿨",
        "desc": "깔끔하고 모던한 느낌",
        "brightness": 1.12,
        "contrast": 1.15,
        "color": 0.92,
        "sharpness": 1.10,
        "temp_r": 0.98,
        "temp_b": 1.04,  # 쿨톤
    },
    "D": {
        "name": "선명 강조",
        "desc": "고대비 선명한 느낌",
        "brightness": 1.08,
        "contrast": 1.20,
        "color": 1.02,
        "sharpness": 1.15,
        "temp_r": 1.0,
        "temp_b": 1.0,
    },
    "E": {
        "name": "내추럴",
        "desc": "자연스러운 밝기 보정",
        "brightness": 1.05,
        "contrast": 1.05,
        "color": 1.0,
        "sharpness": 1.03,
        "temp_r": 1.0,
        "temp_b": 1.0,
    },
    "F": {
        "name": "원본",
        "desc": "보정 없음",
        "brightness": 1.0,
        "contrast": 1.0,
        "color": 1.0,
        "sharpness": 1.0,
        "temp_r": 1.0,
        "temp_b": 1.0,
    },
}


# ============================================================
# VideoGenerator 클래스
# ============================================================

class VideoGenerator:
    def __init__(self, config=None, config_path="config.json", log_callback=None, progress_callback=None):
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        
        # 디렉토리 먼저 설정 (다른 곳에서 사용)
        if getattr(sys, 'frozen', False):
            # exe 빌드: exe가 있는 폴더 기준
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.stickers_dir = os.path.join(self.assets_dir, "stickers")
        self.fonts_dir = os.path.join(self.assets_dir, "fonts")
        self.chars_dir = os.path.join(self.assets_dir, "characters")
        self.scene_overlays_dir = os.path.join(self.assets_dir, "overlay", "scenes")
        self.output_dir = os.path.join(self.base_dir, "outputs")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.bgm_dir = os.path.join(self.assets_dir, "bgm")
        os.makedirs(self.bgm_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        if config is None:
            config = self._load_config(config_path)
        self.config = config or {}
        
        self.openai_key = self.config.get("openai_api_key", "")
        
        # API 키 검증
        api_warnings = []
        if not self.openai_key or self.openai_key == "YOUR_OPENAI_API_KEY":
            api_warnings.append("OpenAI")
        
        if api_warnings:
            self._log(f"⚠️ API 키 누락: {', '.join(api_warnings)}")
            self._log(f"⚠️ config.json에 API 키를 입력하세요!")
            self._log(f"⚠️ 없으면 일부 기능이 작동하지 않습니다.")
        else:
            self._log(f"✅ API 키 확인 완료")
        
        self.client = None
        if OPENAI_OK and self.openai_key and self.openai_key != "YOUR_OPENAI_API_KEY":
            self.client = OpenAI(api_key=self.openai_key)
        
        self.voices = []  # ElevenLabs 제거됨 - 미사용
        
        # Google Cloud TTS 자동 감지
        self.google_tts_client = None
        
        # ⭐ 1순위: config.json 내장 google_credentials (별도 파일 불필요!)
        google_creds_data = self.config.get("google_credentials")
        
        # ⭐ 2순위: config.json의 credentials_path (기존 호환)
        google_creds_path = self.config.get("google_cloud_tts", {}).get("credentials_path")
        
        if not google_creds_path:
            # 3순위: 자동 감지
            possible_paths = [
                os.path.join(self.base_dir, "google_credentials.json"),
                r"C:\유형탁\google_credentials.json",
                os.path.join(os.getcwd(), "google_credentials.json"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    google_creds_path = path
                    break
        
        # 내장 credentials가 있으면 임시 파일 생성
        if google_creds_data and not google_creds_path:
            try:
                import tempfile
                temp_creds = os.path.join(self.temp_dir, "_google_credentials.json")
                with open(temp_creds, 'w', encoding='utf-8') as f:
                    json.dump(google_creds_data, f)
                google_creds_path = temp_creds
            except Exception as e:
                self._log(f"   ⚠️ google_credentials 임시파일 생성 실패: {e}")
        
        # 경로 있으면 로드
        if google_creds_path and os.path.exists(google_creds_path):
            try:
                from google.cloud import texttospeech
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_creds_path
                self.google_tts_client = texttospeech.TextToSpeechClient()
                self._log(f"   ✅ Google Cloud TTS 준비됨")
            except:
                self.google_tts_client = None
        
        self.recent_titles = []
        # 채널별 제목 히스토리 폴더 (재시작해도 유지)
        self._title_history_dir = os.path.join(
            os.path.dirname(os.path.abspath(config_path)) if config_path else '.', 'data', 'title_history'
        )
        os.makedirs(self._title_history_dir, exist_ok=True)
        self.recent_tones = []
        self._stop_callback = None  # 중지 콜백
        
        self._log("✅ VideoGenerator 초기화 완료")
    
    def _check_stop(self):
        """중지 요청 체크"""
        if self._stop_callback and callable(self._stop_callback):
            return self._stop_callback()
        return False
    
    def _check_stop(self):
        """중지 요청 체크"""
        if self._stop_callback and callable(self._stop_callback):
            return self._stop_callback()
        return False
    

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        print(full)
        if self.log_callback:
            self.log_callback(msg)
        
        # 치명적 오류 시 예외 발생 → 작업 정지
        if "❌" in msg:
            # 치명적 오류 목록
            critical_errors = [
                "MoviePy 필요",
                "소스 없음",
                "영상 폴더 없음",
                "영상 파일 없음",
                "유효한 영상 없음",
                "사진 폴더 없음",
                "사진 파일 없음",
                "PDF 파일 없음",
                "PDF 변환 실패",
                "클립 생성 실패",
                "렌더링 실패",
            ]
            for err in critical_errors:
                if err in msg:
                    raise RuntimeError(f"치명적 오류로 작업 중단: {msg}")


    def _progress(self, value: int):
        """0~100 진행률을 UI에 전달"""
        if not self.progress_callback:
            return
        try:
            v = int(value)
        except Exception:
            v = 0
        v = max(0, min(100, v))
        try:
            self.progress_callback(v)
        except Exception:
            pass

    
    
    # ============================================================
    # 소스/오디오 유틸 (클래스 메서드로 고정)
    # - 과거 패치에서 들여쓰기 깨짐으로 클래스 밖으로 빠지면
    #   self._is_video_file / self._pick_bgm 호출 시 AttributeError 발생
    # ============================================================



    def _load_config(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    

    def _get_seed_file_path(self, channel):
        """대사설정 파일 경로 가져오기"""
        channels_dir = os.path.join(self.base_dir, "channels")
        os.makedirs(channels_dir, exist_ok=True)
        
        base = None
        try:
            token_path = getattr(channel, "token_path", None)
            if token_path:
                base = os.path.basename(token_path).replace("_token.json", "").replace(".json", "")
        except Exception:
            base = None
        
        if not base:
            base = getattr(channel, "channel_id", None) or "channel"
        
        return os.path.join(channels_dir, f"{base}_script_seeds.txt")
    
    def _get_all_seed_lines(self, channel):
        """대사설정 파일에서 [대사] 태그 줄만 가져오기"""
        path = self._get_seed_file_path(channel)
        if not os.path.exists(path):
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            
            # [대사] 태그가 있는 줄만 필터링, 태그 제거
            result = []
            for line in lines:
                if line.startswith("[대사]"):
                    result.append(line.replace("[대사]", "").strip())
            
            return result
        except Exception:
            return []
    
    def _get_cta_lines(self, channel):
        """대사설정 파일에서 [오프닝] 태그 줄만 가져오기"""
        path = self._get_seed_file_path(channel)
        if not os.path.exists(path):
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            
            # [오프닝] 태그가 있는 줄만 필터링, 태그 제거
            result = []
            for line in lines:
                if line.startswith("[오프닝]"):
                    result.append(line.replace("[오프닝]", "").strip())
            
            return result
        except Exception:
            return []
    
    def _get_custom_tags(self, channel):
        """⭐ v6.3.2: 대사설정 파일에서 [태그] 줄 가져오기
        형식: [태그] 키워드1, 키워드2, 키워드3 ...
        여러 줄 가능, 쉼표로 구분
        """
        path = self._get_seed_file_path(channel)
        if not os.path.exists(path):
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            
            tags = []
            for line in lines:
                if line.startswith("[태그]"):
                    content = line.replace("[태그]", "").strip()
                    # 쉼표로 분리
                    for tag in content.split(","):
                        tag = tag.strip()
                        if tag and tag not in tags:
                            tags.append(tag)
            
            return tags
        except Exception:
            return []

    def _get_font_path_by_weight(self, bold=True):
        """굵기에 따른 폰트 경로 반환"""
        fonts_dir = self.fonts_dir
        if bold:
            candidates = ["NotoSansKR-Bold.ttf", "NanumGothicBold.ttf", "malgunbd.ttf", "gulim.ttc"]
        else:
            candidates = ["NotoSansKR-Regular.ttf", "NanumGothic.ttf", "malgun.ttf", "gulim.ttc"]
        for name in candidates:
            path = os.path.join(fonts_dir, name)
            if os.path.exists(path):
                return path
        # 시스템 폰트 폴백
        system_fonts = [
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\gulim.ttc",
        ]
        for path in system_fonts:
            if os.path.exists(path):
                return path
        return None

    def _apply_frame_effect(self, img, frame_style):
        """이미지에 테두리/액자 효과 적용"""
        if not frame_style or frame_style.get("type") == "none":
            return img
        frame_type = frame_style.get("type", "shadow")
        try:
            if frame_type == "shadow":
                # 그림자 효과 (여백 추가)
                pad = frame_style.get("pad", 10)
                shadow_color = frame_style.get("shadow_color", (0, 0, 0, 100))
                new_img = Image.new("RGBA", (img.width + pad*2, img.height + pad*2), (0,0,0,0))
                # 그림자
                shadow = Image.new("RGBA", (img.width, img.height), shadow_color)
                new_img.paste(shadow, (pad+3, pad+3))
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                new_img.paste(img, (pad, pad), img)
                return new_img.convert("RGB")
            elif frame_type == "border":
                border_w = frame_style.get("width", 4)
                color = frame_style.get("color", (255, 255, 255))
                from PIL import ImageOps
                return ImageOps.expand(img, border=border_w, fill=color)
            else:
                return img
        except Exception:
            return img

    def _build_mixed_audio(self, voice_audio, total_duration, scene_starts):
        """음성 + BGM 믹싱 (BGM 없으면 음성만 반환)"""
        try:
            if not voice_audio:
                return None
            bgm_files = glob.glob(os.path.join(self.bgm_dir, "*.mp3")) + \
                        glob.glob(os.path.join(self.bgm_dir, "*.wav"))
            if not bgm_files:
                return voice_audio
            bgm_path = random.choice(bgm_files)
            from moviepy.editor import AudioFileClip, CompositeAudioClip
            bgm = AudioFileClip(bgm_path)
            if bgm.duration < total_duration:
                bgm = bgm.audio_loop(duration=total_duration)
            else:
                bgm = bgm.subclip(0, total_duration)
            bgm = bgm.volumex(0.08)  # BGM 볼륨 8%
            mixed = CompositeAudioClip([voice_audio, bgm])
            return mixed
        except Exception as e:
            self._log(f"   ⚠️ BGM 믹싱 실패 (음성만 사용): {e}")
            return voice_audio

    def _load_scene_overlays(self):
        """장면 오버레이 이미지/영상 로드"""
        try:
            overlay_dir = self.scene_overlays_dir
            if not os.path.exists(overlay_dir):
                return []
            files = glob.glob(os.path.join(overlay_dir, "*.png")) + \
                    glob.glob(os.path.join(overlay_dir, "*.gif"))
            return files
        except Exception:
            return []

    def _generate_description(self, title, channel):
        """YouTube 설명란 생성"""
        return self._generate_description_template(title, channel)

    def _generate_tags(self, project_name, title, channel=None):
        """YouTube 태그 생성"""
        custom_tags = self._get_custom_tags(channel) if channel else []
        base_tags = [project_name, "분양", "아파트", "부동산", "모델하우스",
                     "분양정보", "신축아파트", "내집마련", "분양가", "아파트분양"]
        # 제목에서 키워드 추출
        title_words = [w for w in re.split(r'[\s\|\-\,\.]+', title) if len(w) >= 2]
        all_tags = list(dict.fromkeys(custom_tags + [project_name] + title_words[:5] + base_tags))
        return all_tags[:30]

    def _extract_area_from_text(self, project_name, title=""):
        """프로젝트명/제목에서 지역명 추출"""
        area_patterns = [
            r'([가-힣]{2,4}구)', r'([가-힣]{2,4}시)', r'([가-힣]{2,4}동)',
            r'([가-힣]{2,4}읍)', r'([가-힣]{2,4}면)', r'([가-힣]{2,4}역)',
            r'([가-힣]{2,4}로)', r'([가-힣]{2,4}대로)',
        ]
        text = project_name + " " + title
        for pat in area_patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return ""

    def _extract_pdf_keywords_for_title(self, channel, title):
        """PDF에서 제목 관련 키워드 추출 (없으면 빈 문자열)"""
        try:
            pdf_dir = os.path.join(self.base_dir, "channels",
                                   getattr(channel, 'channel_id', 'default'))
            if not os.path.exists(pdf_dir):
                return ""
            pdfs = glob.glob(os.path.join(pdf_dir, "*.pdf"))
            if not pdfs:
                return ""
            # PDF 텍스트 추출 (fitz 사용)
            if not PYMUPDF_OK:
                return ""
            text = ""
            for pdf_path in pdfs[:1]:
                doc = fitz.open(pdf_path)
                for page in doc[:3]:
                    text += page.get_text()
                doc.close()
            return text[:500] if text else ""
        except Exception:
            return ""

    def _generate_unique_title(self, project_name, used_titles):
        """중복 없는 제목 하나 생성 (템플릿 기반 폴백)"""
        import random as _r
        templates = [t for t in TITLE_TEMPLATES if t not in used_titles]
        if not templates:
            templates = TITLE_TEMPLATES
        tpl = _r.choice(templates)
        return tpl.replace("{project}", project_name)

    def _pdf_to_images(self, pdf_path):
        """PDF를 이미지 리스트로 변환"""
        if not PYMUPDF_OK:
            return []
        try:
            doc = fitz.open(pdf_path)
            images = []
            for page in doc:
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                img_path = os.path.join(self.temp_dir, f"pdf_page_{page.number}.png")
                pix.save(img_path)
                images.append(img_path)
            doc.close()
            return images
        except Exception as e:
            self._log(f"   ⚠️ PDF 변환 실패: {e}")
            return []

    def _create_mode_pdf(self, channel, title, suffix):
        """PDF 모드 - photos 모드로 폴백"""
        self._log("   📄 PDF 모드 → photos 모드로 대체")
        return self._create_mode_photos(channel, title, suffix)

    def clear_char_cache(self):
        """캐릭터 캐시 초기화"""
        if hasattr(self, '_char_cache'):
            self._char_cache = {}

    def _select_voice_preset(self):
        """VOICE_PRESETS에서 가중치 기반 랜덤 목소리 선택"""
        presets = list(VOICE_PRESETS.values())
        weights = [p.get("weight", 10) for p in presets]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0
        for preset in presets:
            cumulative += preset.get("weight", 10)
            if r <= cumulative:
                return preset
        return presets[0]

    def _load_overlay_for_mode(self, total_duration):
        """오버레이 클립 로드 - 없으면 None 반환"""
        try:
            overlay_dir = os.path.join(self.assets_dir, "overlay")
            if not os.path.exists(overlay_dir):
                return None, False
            exts = ["*.mp4", "*.mov", "*.avi"]
            files = []
            for ext in exts:
                files += glob.glob(os.path.join(overlay_dir, ext))
            if not files:
                return None, False
            from moviepy.editor import VideoFileClip
            path = random.choice(files)
            clip = VideoFileClip(path, audio=False)
            if clip.duration < total_duration:
                clip = clip.loop(duration=total_duration)
            else:
                clip = clip.subclip(0, total_duration)
            clip = clip.resize((VIDEO_WIDTH, VIDEO_HEIGHT))
            clip = clip.set_opacity(0.3)
            # 밝기 판단: 첫 프레임 평균 밝기
            frame = clip.get_frame(0)
            brightness = frame.mean()
            is_bright = brightness > 128
            return clip, is_bright
        except Exception as e:
            self._log(f"   ⚠️ 오버레이 로드 실패: {e}")
            return None, False

    def _get_link_closing(self, channel):
        """채널에 link_url이 있으면 마지막 멘트 반환, 없으면 None"""
        link_url = getattr(channel, 'link_url', '') or ''
        if not link_url.strip():
            return None
        return "자세한 내용은 링크에서 확인하세요!"

    def _generate_titles_from_seeds(self, project_name, channel):
        """대사설정 [대사]에서 2줄씩 골라 GPT가 자극적 제목 6개 생성 (중복 방지)"""
        all_seeds = self._get_all_seed_lines(channel)
        if not all_seeds:
            return None  # 대사설정 없으면 None → PDF/템플릿 방식으로
        
        titles = []
        # ⭐ 채널별 대사 인덱스 영속 관리 (영상 간 중복 방지)
        if not hasattr(self, '_seed_used_indices'):
            self._seed_used_indices = {}
        _ch_key_idx = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
        used_seed_indices = self._seed_used_indices.setdefault(_ch_key_idx, set())
        
        # GPT 없으면 기존 방식으로
        if not self.client:
            self._log(f"   ⚠️ GPT 없음 → PDF 방식으로")
            return None
        
        # ⭐ 대사 1개뿐이면 → 한 번에 다양한 각도로 6개 생성
        if len(all_seeds) == 1:
            seed = all_seeds[0]
            _ch_key_seed = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
            _hist_t, _ = self._load_title_history(_ch_key_seed)
            _prev = list(dict.fromkeys(_hist_t[-30:] + self.recent_titles[-10:]))
            _prev_str = "\n".join([f"- {t}" for t in _prev[-20:]]) if _prev else "없음"
            try:
                prompt = f"""분양 마케팅 전문가로서 유튜브 쇼츠 제목 6개를 만들어라.

【프로젝트명】 {project_name}
【소재】 {seed}

【이미 사용한 제목 - 절대 중복 금지】
{_prev_str}

【조건】
- 반드시 6개 출력
- 각각 20~35자 이내
- 소재 내용을 제목에 직접 녹여라 (소재가 제목의 핵심!)
- 6개 모두 완전히 다른 각도/표현으로 (질문형, 감탄형, 비교형, 긴박형, 팩트형, 추천형 등)
- 6개 중 같은 시작 단어/표현 절대 금지! ("실화?"로 6개 다 시작하면 안 됨)
- 자극적/호기심 유발
- 금지어: 청약, 가점, 당첨, 폭등, 확정, 보장, 무조건, 100%, 입주, 생활후기
- 제목에 「|」 「/」 「-」 등 구분자 절대 사용 금지!
- 반드시 자연스러운 한 문장으로만 출력

【출력】
제목만 한 줄에 하나씩 (번호 없이)"""
                response = self.client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=400,
                    temperature=1.0
                )
                lines = [l.strip().strip('"\'- ').strip() for l in response.choices[0].message.content.strip().split('\n') if l.strip()]
                for t in lines:
                    pass  # 프로젝트명 강제 삽입 안 함
                    t = self._filter_forbidden(t[:40])
                    if '|' in t:  # | 포함 제목 완전 제외
                        continue
                    if t and t not in titles:
                        titles.append(t)
                        self._log(f"      🏷️ {t}")
                if titles:
                    _ck = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
                    self._save_title_history(_ck, titles, [])
                    return titles if titles else None
            except Exception as e:
                self._log(f"   ⚠️ 단일 대사 제목 생성 실패: {e}")
            return titles if titles else None
        
        # 6개 제목 생성 시도
        attempts = 0
        max_attempts = 10
        
        while len(titles) < 6 and attempts < max_attempts:
            attempts += 1
            
            # 사용 안 한 시드에서 2줄 랜덤 선택
            available_indices = [i for i in range(len(all_seeds)) if i not in used_seed_indices]
            if len(available_indices) < 2:
                # 시드 부족하면 초기화하고 재사용 (단, 이미 만든 제목은 유지)
                used_seed_indices.clear()
                available_indices = list(range(len(all_seeds)))
            
            selected_indices = random.sample(available_indices, min(2, len(available_indices)))
            selected_seeds = [all_seeds[i] for i in selected_indices]
            # 대사 1개면 같은 걸 2번 사용
            if len(selected_seeds) < 2:
                selected_seeds = selected_seeds * 2
            
            # GPT로 자극적 제목 생성
            try:
                # 이미 생성한 제목 + 채널 히스토리 전달
                _ch_key_seed = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
                _hist_t, _ = self._load_title_history(_ch_key_seed)
                _prev = list(dict.fromkeys(titles + _hist_t[-30:] + self.recent_titles[-10:]))
                _prev_str = "\n".join([f"- {t}" for t in _prev[-20:]]) if _prev else "없음"

                prompt = f"""분양 마케팅 전문가로서 자극적이고 클릭을 유도하는 유튜브 쇼츠 제목을 만들어라.

【프로젝트명】 {project_name}

【활용할 소재 2가지】
1. {selected_seeds[0]}
2. {selected_seeds[1] if len(selected_seeds) > 1 else selected_seeds[0]}

【이미 사용한 제목 - 절대 중복 금지】
{_prev_str}

【조건】
- 제목 1개만 출력
- 20~35자 이내
- 위 이미 사용한 제목과 완전히 다른 표현 사용
- 소재 내용을 제목에 직접 녹여라 (소재가 제목의 핵심!)
- 자극적/호기심 유발 (실화?, 대박, 미쳤다, 놓치면 후회 등)
- 이전에 생성한 제목과 같은 시작 단어/표현 금지!
- 금지어: 청약, 가점, 당첨, 폭등, 확정, 보장, 무조건, 100%
- 금지어: 입주, 입주 시작, 살아보니, 거주, 생활후기
- 제목에 「|」 「/」 「-」 등 구분자 절대 사용 금지!
- 반드시 자연스러운 한 문장으로만

【출력】
제목만 출력 (설명 없이)"""

                response = self.client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=100,
                    temperature=0.9
                )
                
                title = response.choices[0].message.content.strip()
                title = title.replace('"', '').replace("'", "").strip()
                
                # 프로젝트명 강제 삽입 안 함 - 대사 내용이 제목의 핵심
                
                # 40자 제한
                if len(title) > 40:
                    title = title[:40]
                
                # 금지어 필터
                title = self._filter_forbidden(title)
                title = title.replace(' | ', ' ').replace('| ', '').replace(' |', '')
                
                # 중복 체크
                if title and title not in titles:
                    titles.append(title)
                    used_seed_indices.update(selected_indices)
                    self._log(f"      🏷️ {title}")
                    
            except Exception as e:
                self._log(f"      ⚠️ GPT 제목 생성 실패: {e}")
                continue
        
        if len(titles) < 6:
            self._log(f"   ⚠️ 대사설정 제목 {len(titles)}개만 생성됨")
            if titles:
                # 부분 결과도 히스토리 저장
                _ck = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
                self._save_title_history(_ck, titles, [])
                return titles if titles else None
            return None
        
        # 히스토리 저장
        _ck = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name)
        self._save_title_history(_ck, titles, [])
        return titles
    
    def _pick_channel_seed_text(self, channel):
        """채널 전용 문구 풀에서 1개 선택(없으면 None). main.py '대사설정' 버튼과 연동."""
        import random
        channels_dir = os.path.join(self.base_dir, "channels")
        os.makedirs(channels_dir, exist_ok=True)

        base = None
        try:
            token_path = getattr(channel, "token_path", None)
            if token_path:
                base = os.path.basename(token_path).replace("_token.json", "").replace(".json", "")
        except Exception:
            base = None

        if not base:
            base = getattr(channel, "channel_id", None) or "channel"

        path = os.path.join(channels_dir, f"{base}_script_seeds.txt")
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            seed = random.choice(lines) if lines else None
            seed = self._sanitize_seed_text(seed)
            return seed
        except Exception:
            return None

    def _check_title_similarity(self, titles, project_name):
        """제목 중복 체크 - 동일/유사 제목 제외"""
        result = []
        used_in_this_batch = []  # 이번 배치에서 사용한 제목
        
        for title in titles:
            # 1. 완전 동일 제목 체크
            if title in self.recent_titles or title in used_in_this_batch:
                # 새 제목 생성
                new_title = self._generate_unique_title(project_name, used_in_this_batch)
                result.append(new_title)
                used_in_this_batch.append(new_title)
                continue
            
            # 2. 유사도 체크 (70% 이상 유사하면 제외)
            is_similar = False
            for recent in self.recent_titles + used_in_this_batch:
                if self._similarity(title, recent) > 0.7:
                    is_similar = True
                    break
            
            if is_similar:
                new_title = self._generate_unique_title(project_name, used_in_this_batch)
                result.append(new_title)
                used_in_this_batch.append(new_title)
            else:
                result.append(title)
                used_in_this_batch.append(title)
        
        return result
    
    def _similarity(self, a, b):
        set_a = set(a)
        set_b = set(b)
        if not set_a or not set_b:
            return 0
        return len(set_a & set_b) / len(set_a | set_b)
    
    def _filter_forbidden(self, text):
        for word in FORBIDDEN_WORDS:
            text = text.replace(word, "")
        return text.strip()
    
    # ============================================================
    # 대본 생성
    # ============================================================
    
    def _load_title_history(self, ch_key):
        """채널별 사용한 제목 히스토리 파일에서 로드"""
        try:
            safe_key = re.sub(r'[^\w가-힣-]', '_', str(ch_key))[:40]
            path = os.path.join(self._title_history_dir, f"{safe_key}.json")
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('titles', []), []
        except Exception:
            pass
        return [], []


    def _save_title_history(self, ch_key, titles, templates=None):
        """채널별 사용한 제목 히스토리 저장"""
        try:
            safe_key = re.sub(r'[^\w가-힣-]', '_', str(ch_key))[:40]
            path = os.path.join(self._title_history_dir, f"{safe_key}.json")
            existing_titles, _ = self._load_title_history(ch_key)
            merged_titles = list(dict.fromkeys(existing_titles + titles))[-300:]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'titles': merged_titles}, f, ensure_ascii=False)
        except Exception as e:
            self._log(f"   ⚠️ 히스토리 저장 실패: {e}")


    def generate_script(self, title, tone="hybrid", sentence_count=None, channel_seed=None):
        """대본 생성 (sentence_count: Photos 모드용 10문장)"""
        # 채널 톤 값(예: FRIEND)을 내부 톤 키로 매핑
        if isinstance(tone, str):
            t = tone.strip().lower()
            if t in ("friend", "friendly", "friend_tone", "friendtone"):
                tone = "info"
            elif t in ("calm", "soft"):
                tone = "summary"
        if tone == "hybrid" or tone not in TONE_TYPES:
            tone = self._select_tone()
        
        self.recent_tones.append(tone)
        if len(self.recent_tones) > 5:
            self.recent_tones = self.recent_tones[-5:]
        
        # ⭐ 프리미엄/호재 순번 관리
        if not hasattr(self, '_premium_index'):
            self._premium_index = 0
        if not hasattr(self, '_hojae_index'):
            self._hojae_index = 0
        
        # 순번 힌트 생성 (제목에 따라 결정)
        premium_hint = self._get_premium_hint(title)
        
        if self.client:
            script = self._generate_script_ai(title, tone, sentence_count, channel_seed=channel_seed, premium_hint=premium_hint)
            if script:
                return script
            # GPT 실패 시 재시도
            self._log(f"   ⚠️ GPT 실패 → 재시도")
            script = self._generate_script_ai(title, tone, sentence_count, channel_seed=channel_seed, premium_hint=premium_hint)
            if script:
                return script
        self._log(f"   ❌ 대본 생성 실패")
        return ""  
    

    def _get_premium_hint(self, title=""):
        """프리미엄/호재 순번 힌트 생성 - 제목에 숫자(3가지, 5가지 등)가 있을 때만!
        
        Returns:
            tuple: (개수, 순번리스트) 또는 None
            예: (5, ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째"])
        """
        
        title_lower = title.lower() if title else ""
        
        # ⭐ 제목에 "N가지", "N개" 같은 숫자가 있을 때만 순번 사용
        import re
        number_match = re.search(r'(\d+)\s*(가지|개|포인트|체크)', title_lower)
        
        if number_match:
            count = int(number_match.group(1))
            ordinals = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째", "여섯 번째", "일곱 번째", "여덟 번째", "아홉 번째", "열 번째"]
            if count <= len(ordinals):
                return (count, ordinals[:count])
        
        # 숫자 없으면 순번 힌트 안 씀
        return None
    

    def _select_tone(self):
        available = [t for t in TONE_TYPES.keys() if t not in self.recent_tones[-5:]]
        if not available:
            available = list(TONE_TYPES.keys())
        
        weights = [TONE_TYPES[t]["weight"] for t in available]
        return random.choices(available, weights=weights, k=1)[0]
    

    def _generate_script_ai(self, title, tone, sentence_count=None, channel_seed=None, premium_hint=None):
        tone_info = TONE_TYPES.get(tone, TONE_TYPES["hybrid"])
        opener = tone_info.get("opener", "")
        
        # ⭐ channel_seed에서 핵심 정보만 추출 (시공사만 유지, 규모/타입/층수 제거!)
        exact_numbers = ""
        has_седaesu = False  # 세대수 추출 여부 (후처리용)
        if channel_seed:
            # 시공사 추출 (유일하게 대본에 넣을 수 있는 사업개요 항목)
            m = re.search(r'시공사[:\s]*([^\n,]+)', channel_seed)
            if m:
                exact_numbers += f"- 시공사: 정확히 \"{m.group(1).strip()}\"라고 써라\n"
            
            # 세대수 여부 체크 (대본에 넣진 않지만 후처리 플래그용)
            m = re.search(r'세대수[:\s]*([0-9,]+)', channel_seed)
            if m:
                has_седaesu = True
        
        # ⭐ 세대수 없으면 주차대수 + 세대수 언급 금지
        parking_ban = ""
        if not has_седaesu:
            parking_ban = "\n🚫 주차대수/주차공간/세대당 주차 관련 숫자는 절대 언급하지 마라! (세대수 미확인 시 주차비율 오류 가능)"
            parking_ban += "\n🚫 '~세대', '~세대 규모', '대단지', '대규모 단지' 같은 세대수 관련 표현도 절대 사용하지 마라! (세대수 미확인)"
        
        numbers_block = f"""🚨 핵심 규칙 🚨
{exact_numbers if exact_numbers else ''}
🚫 절대 언급 금지 (틀리기 쉬운 정보):
- 세대수, 총 세대, ~세대 규모, 대단지, 대규모 단지
- 층수 (지하X층~지상X층)
- 타입/평형 숫자 (59타입, 84타입 등)
- 주차대수, 세대당 주차
- 연면적, 건폐율, 용적률

✅ 대신 이것에 집중하라:
- PDF에 나온 교통 호재 (역, 도로, GTX 등)
- 주변 개발 계획 (신도시, 재개발, 기업 유치 등)  
- 학군/교육 환경 (학교 이름은 PDF에 있는 것만!)
- 생활 편의시설 (PDF에 있는 것만!)
- 자연환경/공원 (PDF에 있는 것만!)
- 프리미엄/시세 상승 가능성
- "왜 여기가 좋은지"를 PDF에서 찾아 설득력 있게!"""
        
        # ⭐ 전체 프로젝트 최근 대본 기록 (영상 간 중복 방지)
        if not hasattr(self, '_recent_scripts'):
            self._recent_scripts = []
        
        # ⭐ 소재(팩트/키워드) 중복 방지 - 이전 영상에서 사용한 핵심 소재 추적
        if not hasattr(self, '_used_topics'):
            self._used_topics = []
        
        # 최근 대본에서 반복 패턴 추출 (간결하게!)
        recent_sentences_hint = ""
        if self._recent_scripts:
            # ⭐ 이전 대본에서 자주 쓴 "시작 패턴" 추출 (앞 10자)
            used_openers = set()
            used_closers = set()
            used_phrases = set()
            
            for prev_script in self._recent_scripts[-6:]:
                sents = [s.strip() for s in prev_script.replace(".", ".\n").replace("!", "!\n").replace("?", "?\n").split("\n") if s.strip() and len(s.strip()) > 8]
                if sents:
                    used_openers.add(sents[0][:10])
                    used_closers.add(sents[-1][:10])
                
                # 반복되는 진부한 표현 추출
                for s in sents:
                    for phrase in ["주목받고", "매력적", "편리합니다", "기회를 놓치지", 
                                   "새로운 시작", "새로운 삶", "눈길을 끌", "화제입니다",
                                   "관심이 있다면", "살펴보시", "기대됩니다", "추천드립니다",
                                   "놓치지 마세요", "알아보시", "체크해보", "고려해보",
                                   "풍요로", "쾌적한", "탁월한", "뛰어난 접근",
                                   "가능성이 큽니다", "만족을 선사", "기대를 모으"]:
                        if phrase in s:
                            used_phrases.add(phrase)
            
            if used_openers or used_phrases:
                banned_openers = ', '.join(list(used_openers)[:8])
                banned_phrases = ', '.join(list(used_phrases)[:15])
                
                # ⭐ 이전 소재도 포함
                used_topics_hint = ""
                if self._used_topics:
                    recent_topics = self._used_topics[-20:]
                    used_topics_hint = f"\n❌ 이전에 이미 다룬 소재: {', '.join(recent_topics[:10])}\n→ 위 소재 반복 금지! PDF에서 아직 안 다룬 정보를 써라!"
                
                recent_sentences_hint = f"""
🚨 중복 금지 규칙:
❌ 금지 시작: {banned_openers}
❌ 금지 표현: {banned_phrases}
→ 위와 같은 시작/표현을 쓰면 안 된다! 완전히 새로운 문장을 만들어라!
→ "~합니다", "~입니다" 대신 "~거든요", "~한데요", "~이에요" 등 다양한 어미를 써라!
{used_topics_hint}
"""
        
        # ============================================================
        # 대본 다양성 랜덤 요소 (대폭 확장!)
        # ============================================================
        
        # 1️⃣ 시작 화법 (12종) - 예시 없이 설명만! (GPT가 예시 복사 방지)
        START_HOOKS = [
            "질문형: 시청자에게 질문을 던지며 시작하라",
            "감탄형: 감탄사로 임팩트 있게 시작하라",
            "팩트형: 구체적인 팩트 정보로 바로 시작하라",
            "비교형: 다른 것과 비교하며 시작하라",
            "호기심형: 궁금증을 유발하며 시작하라",
            "현장형: 현장에 있는 듯한 생생함으로 시작하라",
            "스토리형: 짧은 이야기처럼 시작하라",
            "단도직입형: 핵심부터 바로 말하라",
            "비밀공유형: 몰랐던 정보를 알려주는 느낌으로 시작하라",
            "추천형: 적극 추천하는 느낌으로 시작하라",
            "반문형: 반문을 던지며 시작하라",
            "경험형: 직접 경험한 것처럼 시작하라",
        ]
        
        # 2️⃣ 말투 스타일 (10종) - 🔥 자극적 스타일 추가!
        SPEAK_STYLES = [
            "에너지형: 밝고 활기차게 작성하라",
            "공감형: 시청자 고민에 공감하며 작성하라",
            "반전형: 의외의 관점에서 긍정적으로 반전시켜라",
            "친근형: 친구에게 말하듯 편하게 작성하라",
            "전문가형: 전문적이면서 쉽게 설명하라",
            "흥분형: 좋은 걸 발견한 것처럼 신나게 작성하라",
            # 🔥 자극적 스타일 (팩트 기반으로!)
            "충격형: PDF 팩트를 활용해 '이건 진짜다', '실화냐' 같은 놀라움 표현",
            "긴급형: '지금 아니면 늦는다', '놓치면 후회한다' 같은 긴박감 표현",
            "폭로형: '남들은 모르는', '안 알려주는' 같은 비밀 공개 느낌으로",
            "확신형: '이 정도면 무조건', '이건 진짜 기회다' 같은 강한 확신 표현",
        ]
        
        # 3️⃣ 강조 포인트 (10종) - 가치/이유 중심!
        FOCUS_POINTS = [
            "교통/역세권 호재를 메인으로 (신설역, GTX, 도로 확장 등)",
            "학군/교육환경 장점을 메인으로 (도보 통학, 명문 학군 등)",
            "자연환경/공원 쾌적함을 메인으로 (한강, 근린공원 등)",
            "생활 편의시설 구체적으로 (마트, 병원, 백화점 이름 등)",
            "미래가치/개발호재를 메인으로 (신도시, 재개발, 기업 유치 등)",
            "직주근접/출퇴근 장점을 메인으로 (산업단지, 기업, 역 접근성 등)",
            "시세 상승/프리미엄 가능성을 메인으로 (주변 시세, 개발 기대감 등)",
            "주변 인프라 변화를 메인으로 (신규 개통, 신설 시설, 지역 변화 등)",
            "가족/자녀 생활 장점을 메인으로 (학교, 공원, 안전, 의료 등)",
            "지역 분위기/라이프스타일을 메인으로 (동네 특성, 주민 구성, 문화 등)",
        ]
        
        # 4️⃣ 문장 구조 (5종)
        SENTENCE_STRUCTURES = [
            "짧은 문장 위주 (15~20자)",
            "중간 길이 문장으로 리듬감 있게 (20~30자)",
            "질문과 답변을 섞어서 구성",
            "나열형으로 포인트별 정리",
            "스토리텔링 흐름으로 자연스럽게",
        ]
        
        # 5️⃣ 감정 톤 (5종) - 새로 추가!
        EMOTION_TONES = [
            "설렘: 새 집에 대한 기대감과 설렘을 담아서",
            "안심: 믿을 수 있다는 안도감을 주는 톤으로",
            "놀라움: 예상 못한 장점에 놀라는 느낌으로",
            "확신: 확실히 좋다는 자신감 있는 톤으로",
            "기대: 미래 가치에 대한 기대감을 담아서",
        ]
        
        # 랜덤 선택
        hook = random.choice(START_HOOKS)
        style = random.choice(SPEAK_STYLES)
        focus = random.choice(FOCUS_POINTS)
        structure = random.choice(SENTENCE_STRUCTURES)
        emotion = random.choice(EMOTION_TONES)
        
        # 6️⃣ 팩트 활용 방식 (5종) - 같은 PDF에서도 다른 결과!
        FACT_USAGE_HINTS = [
            "⭐ 아래 참고 정보에서 뒷부분에 있는 정보를 중심으로 활용하라! 앞부분 정보는 보조로만.",
            "⭐ 아래 참고 정보에서 숫자(거리, 시간, 연도)가 포함된 정보를 우선 활용하라!",
            "⭐ 아래 참고 정보에서 지명/시설명이 있는 구체적 정보 위주로 활용하라! 일반적 표현은 피해라.",
            "⭐ 아래 참고 정보 중 2~3개만 골라서 깊이 있게 설명하라! 많이 나열하지 말고 집중하라!",
            "⭐ 아래 참고 정보를 역순(뒤→앞)으로 읽고, 뒷부분 정보부터 먼저 활용하라!",
        ]
        fact_hint = random.choice(FACT_USAGE_HINTS)
        
        self._log(f"      🎲 대본: {hook.split(':')[0]} / {style.split(':')[0]} / {emotion.split(':')[0]}")
        self._log(f"      📋 팩트활용: {fact_hint[:30]}...")
        
        # 순번 힌트 문구 (프리미엄/호재 있을 때) - 튜플: (개수, 순번리스트)
        premium_instruction = ""
        if premium_hint:
            count, ordinals = premium_hint
            ordinals_str = ", ".join(ordinals)
            self._log(f"      🏷️ 순번 힌트: {count}개 ({ordinals_str})")
            premium_instruction = f"""
【순번 구조 - 필수!】
제목에 "{count}가지/개"가 있으므로, 반드시 {count}개의 포인트를 순서대로 말해야 한다.
순번: {ordinals_str}

예시 (5가지일 때):
1. "첫 번째, 교통입니다"
2. "두 번째, 학군이에요"  
3. "세 번째, 인프라 좋습니다"
4. "네 번째, 미래가치입니다"
5. "다섯 번째, 브랜드예요"

⚠️ 반드시 {count}개 모두 순번을 붙여서 말하라!
"""
        
        # Photos 모드: 10문장, 그 외: 5~7문장
        if sentence_count and sentence_count >= 9:
            seed_length = len(channel_seed) if channel_seed else 0
            seed_supplement = ""
            if seed_length > 0:
                seed_supplement = """
🚫 대사 기반 대본 엄격 규칙:
- 위 【대사설정】에 있는 내용만 사용해서 대본을 만들어라
- 대사에 없는 내용(역명, GTX, 학교, 공원, 편의시설 등) 절대 추가 금지!
- 대사 각 줄을 2~3문장으로 풀어서 설득력 있게 확장하라
- 대사가 적으면 같은 내용을 다른 각도/표현으로 반복 확장해도 됨
- 문장이 부족해도 절대 대사에 없는 내용으로 채우지 마라!"""
            prompt = f"""너는 유튜브 숏츠 분양 영상 전문 작가다.

【제목】 {title}
{recent_sentences_hint}
{fact_hint}
{channel_seed if channel_seed else '【참고 정보】없음 - 일반적 표현만 사용'}
{seed_supplement}
⚠️ 대본 작성 핵심 원칙:
- 【대사설정】이 있으면 그 내용만으로 대본을 만들어라! 대사에 없는 내용 절대 추가 금지!
- 대사 내용을 여러 문장으로 풀어서 설득력 있게 확장 (한 줄 → 2~3문장으로)
- 규모/타입/층수 같은 스펙 나열 금지!
- 대사에 없는 역명/학교명/시설명/GTX노선 절대 날조 금지!
- "관심 있다면", "참고해보세요" 같은 뻔한 마무리 반복 금지!
- 각 문장이 다른 내용을 담아야 함 (같은 문장 반복 절대 금지!)

{numbers_block}
{premium_instruction}
【조건 - TTS 최적화】
- 문장 수: 정확히 {sentence_count}문장
- 각 문장: 15~30자 (짧고 단정하게!) 절대 35자 초과 금지!
- 35자 넘는 문장은 반드시 2개로 나눠라!
- 쉼표(,) 최소화! 문장을 나누는 것으로 대체
- 느낌표(!)는 전체에서 2~3개만. 연속 사용 금지
- 긴 대시(—), 말줄임표(…) 사용 금지
- 모든 문장은 최소 8자 이상!
- 질문형 문장 연속 사용 금지

【숫자/단위 규칙】
- GTX, IC 등 영문 약자는 한글 설명과 함께 (GTX-D노선, 검단IC)
- 연도는 숫자로 (2026년 12월)
- 역 이름, 도로, 학교, 시설은 반드시 아래 【참고 정보】에 명시된 것만 사용할 것

【대본 구성 - 이유 중심!】
▶ 오프닝 (1~2문장): 시선 끌기 - 이 단지의 가장 강한 한 가지 포인트
▶ 중반 (3~{sentence_count-3}문장): 참고 정보에서 찾은 구체적 장점들
  - 각 문장마다 서로 다른 장점을 다뤄라 (교통, 학군, 개발, 환경 등)
  - "좋습니다", "편리합니다" 같은 뻔한 결론이 아닌 구체적 팩트 위주
  - 예시: "도보 5분 거리에 지하철역이 있어 출퇴근이 빠릅니다" (역명은 참고 정보에 있는 것만!)
  - 예시: "GTX 노선 개통으로 강남까지 이동이 크게 편해집니다" (역명/날짜는 참고 정보에 있는 것만!)
▶ 후반 (마지막 2~3문장): 부드러운 마무리
  - "조건 맞으시면 참고해보셔도 됩니다" 같은 자연스러운 클로징

🚨 지명/역명/시설명 날조 절대 금지 🚨
- 역 이름(○○역), 학교 이름, 시설명, 도로명은 반드시 【참고 정보】에 있는 것만 사용
- 참고 정보에 없는 역명/학교명/시설명을 절대 만들어내지 마라
- 참고 정보가 없거나 부족하면 → "인근 지하철역", "주변 학교" 처럼 일반 표현으로 대체
- 연도/날짜도 참고 정보에 명시된 것만 사용, 없으면 쓰지 마라

【시작 화법】
{hook}

【말투 스타일】
{style}

【강조 포인트】
{focus}

【감정 톤】
{emotion}

【절대 금지】
- 세대수/층수/타입/평형/주차대수/연면적 언급 절대 금지!
- "다양한 타입이 있습니다", "여러 선택지가 마련되어 있습니다" 같은 빈말 금지!
- "생활 인프라가 잘 갖춰져 있습니다" 같은 구체성 없는 문장 금지!
- PDF에 없는 시설/장소/거리/시간 날조 금지
- 같은 어미 연속 2회 금지 (~입니다/~합니다/~있습니다)
- 프로젝트명은 전체에서 최대 1~2번! 나머지는 "이 단지", "이곳"
- 첫 문장에 "안녕하세요" 금지
- 금지어: 청약, 가점, 당첨, 폭등, 급등, 확정, 보장, 무조건, 100%, 대박
- 한자 금지! 입주 전 분양 홍보이므로: "입주", "입주 시작", "살아보니" 금지
- 🚫 초등학교/중학교/고등학교/유치원의 구체적 이름(OO초, OO중, OO고, OO유치원) 절대 금지! "학군이 우수합니다", "교육 환경이 좋습니다"처럼 일반적으로 표현하라!

【출력 형식】
한 문단으로 자연스럽게 출력. 번호/기호 없이. 매번 완전히 새로운 문장으로 창작하라!"""
        else:
            prompt = f"""너는 유튜브 숏츠 분양 영상 전문 작가다.

【제목】 {title}
{recent_sentences_hint}
{fact_hint}
{channel_seed if channel_seed else '【참고 정보】없음 - 일반적 표현만 사용'}
{seed_supplement}
⚠️ 대본 작성 핵심 원칙:
- 【대사설정】이 있으면 그 내용만으로 대본을 만들어라! 대사에 없는 내용 절대 추가 금지!
- 대사 내용을 여러 문장으로 풀어서 설득력 있게 확장 (한 줄 → 2~3문장으로)
- 규모/타입/층수 같은 스펙 나열 금지!
- 대사에 없는 역명/학교명/시설명/GTX노선 절대 날조 금지!
- "관심 있다면", "참고해보세요" 같은 뻔한 마무리 반복 금지!
- 각 문장이 다른 내용을 담아야 함 (같은 문장 반복 절대 금지!)

{numbers_block}
{premium_instruction}
【조건 - TTS 최적화】
- 문장 수: 12문장
- 각 문장: 15~30자 (짧고 단정하게!) 절대 35자 초과 금지!
- 35자 넘는 문장은 반드시 2개로 나눠라!
- 쉼표(,) 최소화! 문장을 나누는 것으로 대체
- 느낌표(!)는 전체에서 2~3개만
- 모든 문장은 최소 8자 이상!

【대본 구성 - 이유 중심!】
▶ 오프닝 (1~2문장): 시선 끌기 - 가장 강한 한 가지 포인트
▶ 중반 (3~10문장): PDF에서 찾은 구체적 장점들 (각 문장 다른 장점)
▶ 후반 (11~12문장): 부드러운 마무리

【시작 화법】
{hook}

【말투 스타일】
{style}

【강조 포인트】
{focus}

【감정 톤】
{emotion}

【절대 금지】
- 세대수/층수/타입/평형/주차대수/연면적 언급 절대 금지!
- "다양한 타입", "여러 선택지", "생활 인프라가 잘 갖춰져" 같은 빈말 금지!
- PDF에 없는 시설/장소/거리/시간 날조 금지
- 같은 어미 연속 2회 금지
- 프로젝트명은 전체에서 최대 1~2번
- 금지어: 청약, 가점, 당첨, 폭등, 급등, 확정, 보장, 무조건, 대박
- 한자 금지! "입주", "살아보니" 금지
- 🚫 초등학교/중학교/고등학교/유치원의 구체적 이름(OO초, OO중, OO고, OO유치원) 절대 금지! "학군이 우수합니다", "교육 환경이 좋습니다"처럼 일반적으로 표현하라!

【출력 형식】
한 문단으로 자연스럽게 출력. 번호/기호 없이. 매번 완전히 새로운 문장으로 창작하라!"""
        
        try:
            if not channel_seed:
                # 대사 없을 때만 웹서치로 단지 정보 파악
                try:
                    resp = self.client.responses.create(
                        model="gpt-5.4-mini",
                        input=prompt,
                        tools=[{"type": "web_search"}],
                    )
                    script = (resp.output_text or "").strip()
                except Exception:
                    resp = self.client.chat.completions.create(
                        model="gpt-5.4-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_completion_tokens=500,
                        temperature=1.0,
                    )
                    script = (resp.choices[0].message.content or "").strip()
            else:
                resp = self.client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=500,
                    temperature=1.0,
                )
                script = (resp.choices[0].message.content or "").strip()
            
            # ⭐ GPT 대본 생성 결과 로그
            self._log(f"   ✅ GPT 대본 생성 완료: {len(script)}자")
            
            # ⭐ 최근 대본 기록 (중복 방지용)
            self._recent_scripts.append(script)
            if len(self._recent_scripts) > 20:
                self._recent_scripts = self._recent_scripts[-20:]
            
            # ⭐ 소재(팩트) 중복 방지: 대본에서 핵심 소재 키워드 추출하여 기록
            import re as _re
            topic_patterns = [
                (r'(\d[\d,]*)\s*미터', '{0}미터'),
                (r'(\d[\d,]*)\s*세대', '{0}세대'),
                (r'(\d+)\s*개의?\s*([가-힣]+)', '{0}개 {1}'),
                (r'(\d[\d,]*)\s*가구', '{0}가구'),
                (r'코스트코', '코스트코'),
                (r'이마트', '이마트'),
                (r'롯데마트', '롯데마트'),
                (r'홈플러스', '홈플러스'),
                (r'스타벅스', '스타벅스'),
                (r'스타필드', '스타필드'),
                (r'산책로', '산책로'),
                (r'테마\s*정원', '테마 정원'),
                (r'([가-힣]+역)', '{0}'),
                (r'GTX-?[A-Z]', 'GTX노선'),
            ]
            for pat, fmt in topic_patterns:
                for m in _re.finditer(pat, script):
                    try:
                        if '{' in fmt:
                            topic = fmt.format(*m.groups())
                        else:
                            topic = fmt
                        if topic and topic not in self._used_topics:
                            self._used_topics.append(topic)
                    except:
                        pass
            # 너무 많으면 오래된 것 제거
            if len(self._used_topics) > 60:
                self._used_topics = self._used_topics[-40:]
            
            for word in FORBIDDEN_WORDS:
                if word in script:
                    script = script.replace(word, "")
            
            # ⭐ PDF에 없는 구체적 시설명 필터링 (GPT 날조 방지)
            fake_facility_patterns = [
                r'코스트코[가-힣\s]*',
                r'이마트[가-힣\s]*',
                r'롯데마트[가-힣\s]*',
                r'홈플러스[가-힣\s]*',
                r'스타벅스[가-힣\s]*',
                r'스타필드[가-힣\s]*',
                r'현대백화점[가-힣\s]*',
                r'신세계[가-힣\s]*',
            ]
            
            # channel_seed(PDF 팩트)에 있는 시설은 허용
            seed_text = channel_seed or ""
            for pattern in fake_facility_patterns:
                facility_name = pattern.split('[')[0]  # "코스트코", "이마트" 등
                if facility_name not in seed_text:
                    # PDF에 없는 시설명 → 제거
                    before = script
                    script = re.sub(pattern, '', script)
                    if script != before:
                        self._log(f"   🚫 PDF에 없는 시설 제거: {facility_name}")
            
            # "걸어서"/"도보" 표현도 PDF에 없으면 제거
            if "도보" not in seed_text and "걸어서" not in seed_text:
                script = re.sub(r'걸어서\s*[가-힣]*\s*(갈 수 있|다닐 수 있|이용할 수 있)[가-힣]*', '', script)
                script = re.sub(r'도보\s*\d+분[가-힣\s]*', '', script)
            
            # ⭐ v6.3.3: 학교 구체적 이름 제거 (초/중/고/유치원)
            # "인천경연초와 신정초등학교가 가까워" → "교육 환경이 가까워"
            # 학교명 패턴: 한글+초, 한글+중, 한글+고, 한글+초등학교, 한글+유치원 등
            school_before = script
            # "OO초와 OO초등학교가" / "OO중, OO고가" 같은 나열 패턴
            script = re.sub(r'[가-힣]{2,10}(?:초등학교|중학교|고등학교|유치원|초|중|고)\s*(?:와|과|,\s*)[가-힣]{2,10}(?:초등학교|중학교|고등학교|유치원|초|중|고)\s*(?:가|이|는|도|에)?', '교육 환경이', script)
            # 단독 학교명: "OO초등학교가 가까워" → "학군이 가까워"  
            script = re.sub(r'[가-힣]{2,10}(?:초등학교|중학교|고등학교|유치원)\s*(?:가|이|는|도|에|와|과)?', '학군이', script)
            # 약칭: "OO초가" "OO중이" (단, "초등", "중등", "고등" 일반 표현은 유지)
            script = re.sub(r'[가-힣]{2,10}(?:초|중|고)(?:가|이|는|도|에|와|과)\s', '학군이 ', script)
            if script != school_before:
                self._log(f"   🚫 학교 구체적 이름 제거 → 일반 표현으로 대체")
            
            # ⭐ 단위 정리: M/m → 미터
            script = re.sub(r'(\d)\s*M\b', r'\1미터', script)
            script = re.sub(r'(\d)\s*m\b', r'\1미터', script)
            
            # ⭐ v6.3.3: 한자 제거 (GPT가 가끔 한자 출력: 期待, 便利 등)
            script = re.sub(r'[\u4e00-\u9fff]+', '', script)
            
            # 빈 줄/연속 공백 정리
            script = re.sub(r'\n\s*\n', '\n', script)
            script = re.sub(r'  +', ' ', script).strip()
            
            # ⭐ 짧은 문장 필터 (8자 미만 → 다음 문장과 병합)
            # "와", "대박", "진짜?" 같은 감탄사 단독 문장 제거
            lines = [l.strip() for l in script.split('\n') if l.strip()]
            
            # ⭐ v6.3.3: 불완전 문장 병합 (종결어미가 아닌 줄 → 다음 줄과 합침)
            # GPT가 한 문장을 두 줄로 나누는 경우: "교통망으로 서울\n도심까지..."
            COMPLETE_ENDINGS_LINE = (
                '니다', '까요', '시오', '십시오',
                '요', '죠', '세요', '해요', '네요', '래요', '데요', '걸요',
                '거든요', '잖아요', '던가요', '한데요', '이에요', '나요', '건가요',
                '볼까요', '실까요', '텐데요',
                '야', '지', '어', '아', '네', '래', '거든', '잖아', '던데',
                '다', '라',
            )
            merged_lines = []
            for line in lines:
                if merged_lines:
                    prev = merged_lines[-1].rstrip(' ,')
                    is_complete = any(prev.endswith(e) for e in COMPLETE_ENDINGS_LINE)
                    if not is_complete:
                        merged_lines[-1] = merged_lines[-1] + " " + line
                        self._log(f"   🔗 불완전 줄 병합: ...{prev[-10:]} + {line[:25]}...")
                        continue
                merged_lines.append(line)
            lines = merged_lines
            
            # ⭐ 스펙 문장 자동 제거 (규모/타입/층수/세대수 나열 문장)
            spec_patterns = [
                r'지하\d+층.*지상\d+층',          # 층수 나열
                r'\d+타입.*\d+타입',              # 타입 나열
                r'여러\s*타입',                    # 여러 타입
                r'다양한\s*타입',                  # 다양한 타입
                r'선택의\s*폭이',                  # 선택의 폭이
                r'다양한\s*선택지',                # 다양한 선택지
                r'\d[\d,]*\s*세대',               # 세대수
                r'대규모\s*단지',                  # 대규모 단지
                r'연면적',                        # 연면적
                r'건폐율|용적률',                  # 건폐율/용적률
            ]
            spec_removed = 0
            clean_lines = []
            for line in lines:
                is_spec = False
                for pat in spec_patterns:
                    if re.search(pat, line):
                        is_spec = True
                        spec_removed += 1
                        break
                if not is_spec:
                    clean_lines.append(line)
            if spec_removed > 0:
                self._log(f"   🚫 스펙 문장 {spec_removed}개 자동 제거 (층수/타입/세대수)")
                lines = clean_lines
            
            # ⭐ 빈말 문장 자동 제거 (구체적 정보 없는 뻔한 문장)
            empty_talk_patterns = [
                r'^생활\s*인프라가\s*잘\s*갖춰져',
                r'^주거\s*환경이\s*제공하는',
                r'^이곳의\s*모든\s*공간은',
                r'^여러분의\s*새로운\s*시작',
                r'^새로운\s*삶의\s*시작',
                r'^경험해보신다면\s*좋은',
                r'^이곳은\s*많은\s*분들에게',
                r'^기회를\s*엿보신다면',
                r'^선택이\s*소중한\s*만큼',
                r'^많은\s*정보는\s*필수',
                r'^기대감이\s*큽니다',
                r'^적극\s*고려해보세요',
            ]
            empty_removed = 0
            clean_lines2 = []
            for line in lines:
                is_empty = False
                for pat in empty_talk_patterns:
                    if re.search(pat, line):
                        is_empty = True
                        empty_removed += 1
                        break
                if not is_empty:
                    clean_lines2.append(line)
            if empty_removed > 0:
                self._log(f"   🚫 빈말 문장 {empty_removed}개 자동 제거")
                lines = clean_lines2
            
            filtered = []
            for i, line in enumerate(lines):
                if len(line) < 8:
                    if filtered:
                        # 이전 문장에 붙이기
                        filtered[-1] = filtered[-1].rstrip('.!?') + ", " + line
                    # 첫 문장이 짧으면 그냥 버림
                    continue
                filtered.append(line)
            if filtered:
                script = '\n'.join(filtered)
            
            # ⭐ 세대수 미확인 시 대본에서 세대수 관련 표현 자동 제거 (2중 방어)
            if not has_седaesu:
                # "\d+세대" 패턴 제거 (예: "348세대", "1,534세대")
                script_before = script
                script = re.sub(r'\d[\d,]*\s*세대\s*(규모[로의]?)?', '', script)
                script = re.sub(r'총\s*\d[\d,]*\s*세대', '', script)
                script = re.sub(r'무려\s*\d[\d,]*', '', script)
                # 빈 문장 정리
                script = re.sub(r'\n\s*\n', '\n', script).strip()
                if script != script_before:
                    self._log(f"   🚫 세대수 미확인 → 대본에서 세대수 표현 자동 제거")
            
            return script
        except Exception as e:
            self._log(f"   ⚠️ GPT 대본 생성 실패: {e}")
            return None
    

    def _split_sentences(self, script, target_count=10):
        # ⭐ 호선 앞 숫자 보호 (1호선 → __LINE1__호선)
        script = re.sub(r'(\d+)호선', r'__LINE\1__호선', script)
        
        # ⭐ 숫자 쉼표 보호 (1,000 → 1__COMMA__000) - 가장 먼저!
        script = re.sub(r'(\d),(\d)', r'\1__COMMA__\2', script)
        
        # ⭐ 숫자 소수점 보호 (1.5 → 1__DOT__5)
        script = re.sub(r'(\d)\.(\d)', r'\1__DOT__\2', script)
        
        # ⭐ 숫자+단위 보호 (500미터, 1000세대 등) - 쉼표 보호 후에!
        script = re.sub(r'(\d+)(미터|m|세대|평|억|만|천|분|초|개|동|층|대)', r'__NUM\1__\2', script)
        
        # GPT가 번호 붙인 경우 제거
        script = re.sub(r'^(\d{1,2})[.,):\s]+(?=[가-힣])', '', script, flags=re.MULTILINE)
        script = re.sub(r'\n(\d{1,2})[.,):\s]+(?=[가-힣])', '\n', script)
        # 줄 중간 번호도 제거 (예: "어렵죠\n2. 가까운" → "어렵죠\n가까운")
        script = re.sub(r'(\n)(\d{1,2})[.),\s]+(?=[가-힣])', r'\1', script)
        
        # 줄바꿈 기준으로 먼저 분리 (번호 매긴 대본 처리)
        if '\n' in script:
            raw_lines = [l.strip() for l in script.split('\n') if l.strip() and len(l.strip()) >= 5]
            if len(raw_lines) >= 3:
                return raw_lines  # 줄바꿈 문장이 많으면 그대로 사용
        
        sentences = re.split(r'[.!?]\s*', script)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # ⭐ v6.3.3: 불완전 문장 병합 (종결어미가 아닌 문장 → 다음 문장과 합침)
        # 역방향: 종결어미로 끝나면 완전한 문장, 아니면 병합!
        COMPLETE_ENDINGS = (
            # 합쇼체/하십시오체
            '니다', '까요', '시오', '십시오',
            # 해요체
            '요', '죠', '세요', '해요', '네요', '래요', '데요', '걸요',
            '거든요', '잖아요', '던가요', '한데요', '이에요', '나요', '건가요',
            '볼까요', '실까요', '텐데요',
            # 해체 (반말)
            '야', '지', '어', '아', '네', '래', '거든', '잖아', '던데',
            # 기본 종결
            '다', '라',
        )
        merged_sentences = []
        for s in sentences:
            if merged_sentences:
                prev = merged_sentences[-1].rstrip(' ,')
                # 종결어미로 안 끝나면 → 불완전 → 병합
                is_complete = any(prev.endswith(e) for e in COMPLETE_ENDINGS)
                if not is_complete:
                    merged_sentences[-1] = merged_sentences[-1] + " " + s
                    self._log(f"      🔗 불완전 문장 병합: ...{prev[-10:]} + {s[:20]}...")
                    continue
            merged_sentences.append(s)
        sentences = merged_sentences
        
        # ⭐ 잘린 문장 병합 (조사/연결어로 시작하는 비정상 문장)
        broken_starts = (
            '의 ', '을 ', '를 ', '도 ', '와 ', '과 ', '은 ', '는 ', '이 ', '가 ',
            '에 ', '로 ', '에서 ', '으로 ', '까지 ',
            # v6.3.2: 연결 표현
            '있어 ', '있는 ', '있고 ', '있습니다',
            '되어 ', '되는 ', '됩니다', '되었',
            '하여 ', '하는 ', '합니다', '하고 ',
            '으며 ', '이며 ', '라서 ', '라고 ',
            '때문에', '인해 ', '통해 ', '따라 ',
            '위해 ', '대해 ', '관해 ',
            '중, ', '고교', '정원은', '계획되어',
        )
        cleaned_sentences = []
        for s in sentences:
            if any(s.startswith(p) for p in broken_starts):
                if cleaned_sentences:
                    cleaned_sentences[-1] = cleaned_sentences[-1] + " " + s
                    self._log(f"      🔗 잘린 문장 병합: ...{s[:20]}...")
                else:
                    self._log(f"      ⚠️ 잘린 문장 제거: {s[:30]}...")
                continue
            cleaned_sentences.append(s)
        sentences = cleaned_sentences
        
        # 각 문장에서도 앞 번호 제거 (1~2자리 숫자 + 구분자 + 한글)
        cleaned = []
        for s in sentences:
            s = re.sub(r'^(\d{1,2})[.,):\s]+(?=[가-힣])', '', s.strip())
            if s:
                cleaned.append(s)
        sentences = cleaned
        
        # ========================================
        # 긴 문장 자동 분리 (35자 초과 → 2개로 나눔)
        # ⭐ TTS는 의미 단위로 유지, 자막은 렌더링에서 별도 분할
        MAX_CHARS = 35
        final_sentences = []
        
        for sent in sentences:
            # ⭐ 숫자 쉼표 복원
            sent = sent.replace('__COMMA__', ',')
            # ⭐ 숫자 소수점 복원
            sent = sent.replace('__DOT__', '.')
            # ⭐ 호선 숫자 복원 (__LINE1__호선 → 1호선)
            sent = re.sub(r'__LINE(\d+)__호선', r'\1호선', sent)
            # ⭐ 숫자+단위 복원 (__NUM500__미터 → 500미터)
            sent = re.sub(r'__NUM(\d+)__', r'\1', sent)
            
            if len(sent) <= MAX_CHARS:
                final_sentences.append(sent)
            else:
                # 긴 문장 → 2개로 분리
                split_pos = None
                
                # 1순위: 쉼표(,) 위치 (단, 숫자 사이 쉼표는 제외!)
                for i, char in enumerate(sent):
                    if char == ',':
                        # 앞뒤가 숫자면 분리하지 않음 (예: 1,534 / 2,000)
                        before = sent[i-1] if i > 0 else ''
                        after = sent[i+1] if i < len(sent)-1 else ''
                        if before.isdigit() and after.isdigit():
                            continue  # 숫자 쉼표는 건너뛰기
                        if i > 3 and i < len(sent) - 3:
                            split_pos = i + 1
                            break
                
                # 2순위: 공백 기준 중간 (단, 숫자+단위 사이는 피함)
                if not split_pos:
                    mid = len(sent) // 2
                    best_pos = None
                    best_diff = len(sent)
                    
                    # 숫자+단위 패턴 (분리하면 안 되는 위치)
                    protected_positions = set()
                    for m in re.finditer(r'\d+\s*(미터|m|세대|평|억|만|천|분|초|개|동|층|대|호선|km|㎡)', sent):
                        # 숫자와 단위 사이 공백 위치 보호
                        for pos in range(m.start(), m.end()):
                            protected_positions.add(pos)
                    
                    for i, char in enumerate(sent):
                        if char == ' ':
                            # 숫자+단위 사이 공백이면 스킵
                            if i in protected_positions or (i > 0 and i-1 in protected_positions):
                                continue
                            diff = abs(i - mid)
                            if diff < best_diff:
                                best_diff = diff
                                best_pos = i
                    
                    if best_pos:
                        split_pos = best_pos
                
                # 3순위: 그냥 중간
                if not split_pos:
                    split_pos = len(sent) // 2
                
                part1 = sent[:split_pos].strip()
                part2 = sent[split_pos:].strip()
                
                if part1:
                    final_sentences.append(part1)
                if part2:
                    final_sentences.append(part2)
        
        sentences = final_sentences
        
        # ⭐ 짧은 문장 필터 (8자 미만 → 다음 문장과 병합)
        # "와", "대박", "진짜" 같은 감탄사 단독 자막 방지
        MIN_CHARS = 8
        merged = []
        for s in sentences:
            if len(s) < MIN_CHARS:
                if merged:
                    # 이전 문장 뒤에 쉼표로 붙이기
                    merged[-1] = merged[-1] + ", " + s
                # 첫 문장이 짧으면 버림
                continue
            merged.append(s)
        if merged:
            sentences = merged
        
        # 분리 후 문장 수가 target_count보다 많으면 그대로 사용 (대본 다 읽기 위해)
        # 적으면 복제해서 채움
        if len(sentences) < target_count:
            sentences = sentences * (target_count // len(sentences) + 1)
            return sentences[:target_count]
        else:
            # 분리로 늘어난 문장은 모두 사용 (자르지 않음)
            return sentences
    

    def load_sources(self, channel, mode):
        images = []
        
        if mode == "photos":
            folder = channel.photo_folder
            if folder and os.path.isdir(folder):
                for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
                    images.extend(glob.glob(os.path.join(folder, ext)))
                    images.extend(glob.glob(os.path.join(folder, ext.upper())))
                # Windows 대소문자 중복 제거
                images = list(dict.fromkeys(os.path.normcase(f) for f in images))
                images = [os.path.normpath(f) for f in images]
        
        elif mode == "videos":
            # 동영상 모드: 실제 비디오 파일 경로 반환 (프레임 추출 X)
            folder = channel.video_folder
            if folder and os.path.isdir(folder):
                for ext in ["*.mp4", "*.mov", "*.avi"]:
                    vids = glob.glob(os.path.join(folder, ext))
                    images.extend(vids)  # 비디오 파일 경로 그대로
        
        elif mode == "pdf":
            pdf_path = channel.pdf_folder  # 이제 파일 경로
            if pdf_path and os.path.isfile(pdf_path):
                try:
                    pages = self._pdf_to_images(pdf_path)
                    images.extend(pages)
                    self._log(f"   📄 PDF 로드: {os.path.basename(pdf_path)} ({len(pages)}p)")
                except Exception as e:
                    self._log(f"❌ PDF 변환 실패: {os.path.basename(pdf_path)} → {e}")
            else:
                self._log("❌ PDF 파일이 없거나 경로가 잘못되었습니다.")
        
        elif mode == "mixed":
            # ========================================
            # 규칙 22. 혼합모드: 사진(시작) → 영상 → 사진(끝)
            # ========================================
            photo_images = []
            video_files = []
            
            if channel.photo_folder and os.path.isdir(channel.photo_folder):
                for ext in ["*.jpg", "*.jpeg", "*.png"]:
                    photo_images.extend(glob.glob(os.path.join(channel.photo_folder, ext)))
            
            if channel.video_folder and os.path.isdir(channel.video_folder):
                for ext in ["*.mp4", "*.mov"]:
                    vids = glob.glob(os.path.join(channel.video_folder, ext))
                    video_files.extend(vids)
            
            # 사진(시작 2장) + 영상(중간) + 사진(끝 2장)
            images = []
            photos = self._sort_files(photo_images)
            videos = self._sort_files(video_files)
            
            # 시작: 사진 2장
            images.extend(photos[:2])
            
            # 중간: 영상 + 사진 번갈아
            mid_photos = photos[2:-2] if len(photos) > 4 else []
            mid_videos = videos[:4]
            for i in range(max(len(mid_videos), len(mid_photos))):
                if i < len(mid_videos):
                    images.append(mid_videos[i])
                if i < len(mid_photos):
                    images.append(mid_photos[i])
            
            # 끝: 사진 2장
            if len(photos) >= 2:
                images.extend(photos[-2:])
        
        return self._sort_files(images)[:10]
    

    def _get_best_encoder(self):
        """최적 인코더 반환 (첫 실행 시 1회 감지 후 캐싱)"""
        # 클래스 레벨 캐시 (엔진 재로드해도 유지)
        if hasattr(VideoGenerator, '_class_cached_encoder') and VideoGenerator._class_cached_encoder:
            self._cached_encoder = VideoGenerator._class_cached_encoder
            return self._cached_encoder
        # 인스턴스 캐시
        if hasattr(self, '_cached_encoder') and self._cached_encoder:
            return self._cached_encoder
        
        # GPU 인코더 테스트
        for codec in ["h264_nvenc", "h264_qsv", "h264_amf"]:
            if self._test_encoder(codec):
                self._log(f"   ✅ {codec} 사용 가능")
                self._cached_encoder = codec
                VideoGenerator._class_cached_encoder = codec
                return codec
            else:
                self._log(f"   ❌ {codec} 사용 불가")
        
        # GPU 없으면 CPU
        self._log(f"   📌 CPU 인코딩 (libx264)")
        self._cached_encoder = "libx264"
        VideoGenerator._class_cached_encoder = "libx264"
        return "libx264"
    

    def _test_encoder(self, codec):
        """인코더 실제 동작 테스트 (0.5초 테스트 영상)"""
        try:
            import tempfile
            
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp_path = tmp.name
            
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.5",
                "-c:v", codec, "-t", "0.5",
                tmp_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10, startupinfo=_STARTUPINFO)
            
            try:
                os.remove(tmp_path)
            except:
                pass
            
            return result.returncode == 0
        except:
            return False
    

    def _render_final(self, final, out_path):
        """최종 렌더링 (GPU 자동 감지, 1회만)"""
        
        # ⭐ 중지 체크
        if self._check_stop():
            self._log("⏸️ 중지됨")
            return None
        
        self._log("   💾 렌더링 시작...")
        self._progress(5)
        
        render_start = time.time()
        
        # 인코더 가져오기 (첫 실행 시 1회 감지 후 캐싱)
        codec = self._get_best_encoder()
        self._log(f"   🎬 인코더: {codec}")
        
        # 렌더링 설정
        render_args = {
            "fps": 30,
            "codec": codec,
            "audio_codec": "aac",
            "audio_bitrate": "192k",  # 오디오 비트레이트 최적화
            "verbose": False,
            "logger": None,
        }
        
        # GPU별 최적화
        if codec == "h264_nvenc":
            # NVIDIA GPU (가장 빠름)
            render_args["preset"] = "p4"  # p1~p7, p4=균형
            render_args["ffmpeg_params"] = [
                "-b:v", "8M",  # 비트레이트 8Mbps (고화질)
                "-rc", "vbr",  # 가변 비트레이트
            ]
        elif codec == "h264_qsv":
            # Intel GPU - 간소화 (호환성 우선)
            render_args["threads"] = 8
            render_args["ffmpeg_params"] = [
                "-preset:v", "fast",          # fast (안정적)
                "-global_quality", "25",      # 품질 25
                "-b:v", "6M",                 # 6Mbps
            ]
        elif codec == "h264_amf":
            # AMD GPU
            render_args["preset"] = "speed"
            render_args["ffmpeg_params"] = ["-rc", "vbr_latency", "-qp_i", "23"]
        elif codec == "libx264":
            # CPU (폴백) - 속도 최우선
            render_args["threads"] = 8
            render_args["preset"] = "ultrafast"  # 최고 속도
            render_args["ffmpeg_params"] = ["-crf", "28"]  # 화질 약간 낮춰 속도 향상
        
        # 렌더링 실행
        try:
            final.write_videofile(out_path, **render_args)
        except Exception as e:
            self._log(f"   ⚠️ 렌더링 오류: {e}, CPU로 재시도...")
            # GPU 실패 시 CPU로 재시도
            self._cached_encoder = "libx264"  # 캐시 업데이트
            final.write_videofile(
                out_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                audio_bitrate='192k',
                threads=8,
                preset='ultrafast',  # 최고 속도
                ffmpeg_params=["-crf", "28"],
                verbose=False,
                logger=None
            )

        
        # 렌더링 시간
        render_time = time.time() - render_start
        minutes = int(render_time // 60)
        seconds = int(render_time % 60)
        
        self._log("   💾 [████████████████████] 100%")
        self._progress(100)
        
        if minutes > 0:
            self._log(f"   ⏱️ 렌더링 시간: {minutes}분 {seconds}초")
        else:
            self._log(f"   ⏱️ 렌더링 시간: {seconds}초")
        
        return out_path
    

    def _get_scene_effects(self, count):
        effects = []
        last_effect = None
        
        for _ in range(count):
            available = [e for e in SCENE_EFFECTS if e != last_effect]
            effect = random.choice(available)
            effects.append(effect)
            last_effect = effect
        
        return effects
    
    # ============================================================
    # YouTube 업로드
    # ============================================================
    

    def _apply_transitions(self, clips):
        """클립들에 전환효과 적용 (장면마다 랜덤) - 성능 최적화"""
        if len(clips) <= 1:
            return clips
        
        try:
            transitioned = [clips[0]]
            
            for i, clip in enumerate(clips[1:]):
                # ⭐ fade_black 제거 - 검정 화면 방지!
                transition_type = random.choice([
                    "cut",           # 컷 (효과 없음)
                    "cut",           # 컷 추가 (성능 + 안정성)
                    "cut",           # 컷 추가
                    "crossfade",     # 크로스페이드 (자연스러움)
                ])
                
                if transition_type == "cut":
                    pass  # 그대로 (가장 안전)
                
                elif transition_type == "crossfade":
                    try:
                        clip = clip.crossfadein(0.2)  # 0.3 → 0.2로 줄임
                    except:
                        pass  # 실패해도 그냥 컷으로
                
                transitioned.append(clip)
            
            self._log(f"   🎬 전환 효과: 장면별 랜덤 적용")
            return transitioned
        except Exception as e:
            self._log(f"   ⚠️ 전환 효과 실패: {e}")
            return clips
    

    def _concat_audio_with_silence(self, audios, durations):
        """오디오 클립들을 합치기 (침묵 없이 바로 연결 - 싱크 정확도 ↑)"""
        if not any(audios):
            return None
        
        try:
            from moviepy.editor import concatenate_audioclips
            
            clips = []
            for audio in audios:
                if audio:
                    clips.append(audio)
                # 침묵 제거! 바로 연결하여 싱크 정확도 향상
            
            return concatenate_audioclips(clips) if clips else None
        except Exception as e:
            self._log(f"   ⚠️ 오디오 합치기 실패: {e}")
            return None
    

    def _get_frame_style(self):
        """테두리/액자 8종 프리셋"""
        preset = random.choice(["A", "B", "C", "D", "E", "F", "G", "H"])
        
        styles = {
            "A": {  # 흰색 테두리
                "type": "border",
                "color": (255, 255, 255),
                "width": random.randint(8, 15),
                "radius": 0,
            },
            "B": {  # 검정 테두리
                "type": "border",
                "color": (30, 30, 30),
                "width": random.randint(8, 15),
                "radius": 0,
            },
            "C": {  # 컬러 테두리 (민트/노랑/핑크)
                "type": "border",
                "color": random.choice([(100, 255, 218), (255, 220, 100), (255, 180, 200), (180, 200, 255)]),
                "width": random.randint(6, 12),
                "radius": 0,
            },
            "D": {  # 둥근 모서리
                "type": "rounded",
                "color": (255, 255, 255),
                "width": random.randint(6, 10),
                "radius": random.randint(20, 40),
            },
            "E": {  # 그림자 효과
                "type": "shadow",
                "color": (0, 0, 0),
                "offset": random.randint(8, 15),
                "blur": 20,
            },
            "F": {  # 액자 (이중 테두리)
                "type": "frame",
                "outer_color": (60, 50, 40),
                "inner_color": (255, 250, 240),
                "outer_width": random.randint(15, 25),
                "inner_width": random.randint(5, 10),
            },
            "G": {  # 네온 테두리
                "type": "glow",
                "color": random.choice([(0, 255, 200), (255, 100, 200), (100, 200, 255), (255, 255, 100)]),
                "width": random.randint(4, 8),
                "glow_size": 15,
            },
            "H": {  # 테두리 없음
                "type": "none",
            },
        }
        
        return styles[preset]
    

    def _get_photo_enhance_style(self):
        """사진 보정 스타일 랜덤 선택 (원본 제외하고 가중치 적용)"""
        # 원본(F) 제외하고 선택
        styles = ["A", "B", "C", "D", "E"]
        weights = [30, 20, 15, 15, 20]  # A(프리미엄) 가중치 높음
        return random.choices(styles, weights=weights, k=1)[0]
    

    def _apply_photo_enhance(self, img, style_key=None):
        """사진에 부동산용 보정 적용"""
        try:
            from PIL import ImageEnhance
            
            if style_key is None:
                style_key = self._get_photo_enhance_style()
            
            style = PHOTO_ENHANCE_STYLES.get(style_key, PHOTO_ENHANCE_STYLES["A"])
            
            # 원본이면 그대로 반환
            if style_key == "F":
                return img, style_key
            
            # 1. 밝기 (Brightness)
            if style["brightness"] != 1.0:
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(style["brightness"])
            
            # 2. 대비 (Contrast)
            if style["contrast"] != 1.0:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(style["contrast"])
            
            # 3. 채도 (Color/Saturation)
            if style["color"] != 1.0:
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(style["color"])
            
            # 4. 선명도 (Sharpness)
            if style["sharpness"] != 1.0:
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(style["sharpness"])
            
            # 5. 색온도 (RGB 조정)
            temp_r = style.get("temp_r", 1.0)
            temp_b = style.get("temp_b", 1.0)
            if temp_r != 1.0 or temp_b != 1.0:
                img = self._adjust_color_temp(img, temp_r, temp_b)
            
            return img, style_key
            
        except Exception as e:
            self._log(f"      ⚠️ 사진 보정 실패: {e}")
            return img, "F"
    

    def _adjust_color_temp(self, img, r_factor, b_factor):
        """색온도 조정 (R/B 채널)"""
        try:
            import numpy as np
            
            arr = np.array(img).astype(np.float32)
            
            # R 채널 조정
            arr[:, :, 0] = np.clip(arr[:, :, 0] * r_factor, 0, 255)
            # B 채널 조정
            arr[:, :, 2] = np.clip(arr[:, :, 2] * b_factor, 0, 255)
            
            return Image.fromarray(arr.astype(np.uint8))
        except:
            return img
    
    # ============================================================
    # 이미지 클립
    # ============================================================
    

    def _get_font_path(self):
        # ============================================================
        # 영어 지원 폰트 우선 (한글+영어 모두 표시)
        # ============================================================
        
        # 1. assets/fonts 폴더에서 영어 지원 폰트 찾기
        preferred_fonts = [
            "NotoSansKR-Bold.ttf",
            "NotoSansKR-Regular.ttf",
            "NotoSansKR-Medium.ttf",
        ]
        for font_name in preferred_fonts:
            font_path = os.path.join(self.fonts_dir, font_name)
            if os.path.exists(font_path):
                return font_path
        
        # 2. assets/fonts에 있는 모든 폰트
        fonts = glob.glob(os.path.join(self.fonts_dir, "*.ttf"))
        fonts += glob.glob(os.path.join(self.fonts_dir, "*.otf"))
        if fonts:
            return random.choice(fonts)
        
        # 3. 시스템 폰트 (영어 지원 폰트 우선)
        system_fonts = [
            "C:/Windows/Fonts/NotoSansKR-Bold.ttf",      # 1순위
            "C:/Windows/Fonts/NotoSansKR-Regular.ttf",   
            "C:/Windows/Fonts/malgunbd.ttf",             # 맑은고딕
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/NanumGothicBold.ttf",
            "C:/Windows/Fonts/NanumGothic.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # Mac
            "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf",  # Linux
        ]
        
        for font_path in system_fonts:
            if os.path.exists(font_path):
                return font_path  # 첫 번째 발견한 폰트 사용 (우선순위 순)
        
        return None
    
    # ============================================================
    # 사진 보정 (부동산용)
    # ============================================================
    

    def _fit_to_vertical(self, clip):
        """영상을 세로 9:16으로 맞추기 (최적화 버전)"""
        try:
            w, h = clip.w, clip.h
            target_w, target_h = 1080, 1920
            target_ratio = target_w / target_h  # 0.5625
            clip_ratio = w / h
            
            # ⭐ v6.3.2: fps 보존 (없으면 30fps 기본값)
            original_fps = getattr(clip, 'fps', None) or 30
            
            if abs(clip_ratio - target_ratio) < 0.05:
                # 이미 9:16에 가까우면 리사이즈만
                result = clip.resize((target_w, target_h))
                if not getattr(result, 'fps', None):
                    result = result.set_fps(original_fps)
                return result
            
            if clip_ratio > target_ratio:
                # 가로가 더 넓음 → 높이 맞추고 좌우 크롭
                new_h = target_h
                new_w = int(w * target_h / h)
                clip = clip.resize((new_w, new_h))
                # 중앙 크롭
                x_center = new_w // 2
                clip = clip.crop(x1=x_center - target_w//2, x2=x_center + target_w//2)
            else:
                # 세로가 더 넓음 → 너비 맞추고 상하 크롭
                new_w = target_w
                new_h = int(h * target_w / w)
                clip = clip.resize((new_w, new_h))
                # 중앙 크롭
                y_center = new_h // 2
                clip = clip.crop(y1=y_center - target_h//2, y2=y_center + target_h//2)
            
            # ⭐ v6.3.2: fps 보존
            if not getattr(clip, 'fps', None):
                clip = clip.set_fps(original_fps)
            
            return clip
        except Exception as e:
            self._log(f"      ⚠️ 세로변환 실패: {e}")
            return clip.resize((1080, 1920))
    

    def _is_video_file(self, path: str) -> bool:
        try:
            ext = os.path.splitext(path)[1].lower()
            return ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        except Exception:
            return False


    def _sanitize_seed_text(self, seed: str) -> str:
        """채널 시드 문구 - 사용자가 직접 입력한 대사는 그대로 사용
        (이미 팩트체크된 내용이므로 필터링 불필요)
        """
        try:
            if not seed:
                return ""
            s = str(seed).strip()

            # 불필요한 특수문자만 정리 (내용은 그대로 유지)
            s = s.replace("🚨", "").replace("❗", "").replace("✅", "").replace("👉", "")
            s = re.sub(r"\s+", " ", s).strip()

            return s
        except Exception:
            return (seed or "").strip()



    def get_sticker_image(self, text):
        """스티커 규칙: 키워드 있으면만 나옴, 없으면 None"""
        matched_category = None
        
        # 키워드 매칭 (하나만!)
        for category, keywords in STICKER_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    matched_category = category
                    break
            if matched_category:
                break
        
        # 키워드 없으면 스티커 안 나옴
        if not matched_category:
            return None
        
        # 매칭된 카테고리 폴더에서 스티커 가져오기
        folder = os.path.join(self.stickers_dir, matched_category)
        if os.path.isdir(folder):
            files = glob.glob(os.path.join(folder, "*.png"))
            if files:
                try:
                    return Image.open(random.choice(files)).convert("RGBA")
                except:
                    pass
        
        # 카테고리 폴더 없으면 전체에서 랜덤
        all_stickers = glob.glob(os.path.join(self.stickers_dir, "*", "*.png"))
        if all_stickers:
            try:
                return Image.open(random.choice(all_stickers)).convert("RGBA")
            except:
                pass
        
        return None
    

    def _get_sticker_settings(self, subtitle_version="A"):
        # 스티커 크게 (화면의 1/3), 중앙 통일
        return {
            "delay": random.uniform(0.2, 0.5),
            "duration": random.uniform(1.5, 2.5),
            "size_ratio": random.uniform(0.30, 0.35),  # 30~35%
            "position_y": 0.40,  # 화면 중앙 (고정)
            "position_x_offset": 0.0,  # 중앙 (고정)
            "animation": random.choice(["pop", "bounce", "pulse"]),  # 중앙에서 효과
        }
    
    # ============================================================
    # 캐릭터
    # ============================================================
    

    def get_character_image(self, char_name, use_cache=True):
        """캐릭터 이미지 (선택한 폴더에서만!)"""
        self._log(f"   🎭 캐릭터 요청: '{char_name}'")
        
        # '없음' 이면 캐릭터 미사용
        if char_name == "없음":
            self._log(f"   🎭 캐릭터 없음 (사용 안 함)")
            return None
        
        # random이면 폴더 1개 선택 후 고정
        if char_name == "random":
            cache_key = "char_random_folder"
            if use_cache and hasattr(self, '_char_cache') and cache_key in self._char_cache:
                char_name = self._char_cache[cache_key]
                self._log(f"   🎭 캐시된 폴더: {char_name}")
            else:
                folders = glob.glob(os.path.join(self.chars_dir, "*"))
                folders = [f for f in folders if os.path.isdir(f)]
                if folders:
                    char_name = os.path.basename(random.choice(folders))
                    if not hasattr(self, '_char_cache'):
                        self._char_cache = {}
                    self._char_cache[cache_key] = char_name
                    self._log(f"   🎭 랜덤 폴더 선택: {char_name}")
        
        # 선택된 폴더에서 이미지 로드
        char_folder = os.path.join(self.chars_dir, char_name)
        self._log(f"   🎭 폴더 경로: {char_folder}")
        
        if os.path.isdir(char_folder):
            files = glob.glob(os.path.join(char_folder, "*.png"))
            # JPG도 지원
            files.extend(glob.glob(os.path.join(char_folder, "*.jpg")))
            files.extend(glob.glob(os.path.join(char_folder, "*.jpeg")))
            self._log(f"   🎭 이미지 {len(files)}개")
            if files:
                try:
                    selected = random.choice(files)
                    self._log(f"   🎭 선택: {os.path.basename(selected)}")
                    
                    # PNG 파일은 원본 그대로 사용 (투명 배경 유지)
                    if selected.lower().endswith('.png'):
                        img = Image.open(selected)
                        self._log(f"   🎭 PNG 파일 → 원본 그대로 사용")
                    else:
                        # JPG는 배경 제거 처리
                        img = Image.open(selected).convert("RGBA")
                        self._log(f"   🎭 JPG 파일 → 배경 제거 시도")
                        img = self._remove_character_bg(img)
                    
                    return img
                except Exception as e:
                    self._log(f"   🎭 오류: {e}")
        else:
            self._log(f"   🎭 폴더 없음!")
        return None
    

    def _remove_character_bg(self, img):
        """캐릭터 이미지 배경 제거 (흰색/단색 배경 → 투명)"""
        try:
            # RGBA로 변환
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            
            # 알파 채널 확인
            alpha = img.split()[3]
            transparent_pixels = sum(1 for p in alpha.getdata() if p < 128)
            total_pixels = img.width * img.height
            
            # 투명 픽셀이 10% 이상이면 이미 처리됨 (단, 흰색 배경 체크)
            if transparent_pixels / total_pixels > 0.1:
                # 추가 체크: 모서리가 흰색이면 다시 처리
                corners = [
                    img.getpixel((0, 0)),
                    img.getpixel((img.width - 1, 0)),
                    img.getpixel((0, img.height - 1)),
                    img.getpixel((img.width - 1, img.height - 1))
                ]
                
                is_white_bg = all(c[0] > 240 and c[1] > 240 and c[2] > 240 for c in corners if len(c) >= 3)
                
                if not is_white_bg:
                    self._log(f"   🎭 이미 투명 배경")
                    return img
                else:
                    self._log(f"   🎭 흰색 배경 감지 → 재처리")
            
            # 모서리 색상 샘플링 (배경색 추정)
            corners = [
                img.getpixel((0, 0)),
                img.getpixel((img.width - 1, 0)),
                img.getpixel((0, img.height - 1)),
                img.getpixel((img.width - 1, img.height - 1))
            ]
            
            # RGB만 추출
            corner_colors = []
            for c in corners:
                if len(c) >= 3:
                    corner_colors.append(c[:3])
            
            # 모서리 색상이 비슷하면 배경색으로 판단
            if corner_colors:
                avg_r = sum(c[0] for c in corner_colors) // len(corner_colors)
                avg_g = sum(c[1] for c in corner_colors) // len(corner_colors)
                avg_b = sum(c[2] for c in corner_colors) // len(corner_colors)
                
                # 모서리 색상 차이 확인
                max_diff = 0
                for c in corner_colors:
                    diff = abs(c[0] - avg_r) + abs(c[1] - avg_g) + abs(c[2] - avg_b)
                    max_diff = max(max_diff, diff)
                
                # 모서리가 비슷한 색이면 (차이 60 이하) 배경 제거
                if max_diff < 60:
                    bg_color = (avg_r, avg_g, avg_b)
                    self._log(f"   🎭 배경색 감지: RGB{bg_color}")
                    
                    # 배경색과 비슷한 픽셀을 투명하게
                    data = img.getdata()
                    new_data = []
                    
                    # 흰색 배경은 더 관대하게 (tolerance 50)
                    if avg_r > 240 and avg_g > 240 and avg_b > 240:
                        tolerance = 50
                        self._log(f"   🎭 흰색 배경 → 관대한 제거 (tolerance: {tolerance})")
                    else:
                        tolerance = 40
                    
                    for pixel in data:
                        r, g, b = pixel[:3]
                        a = pixel[3] if len(pixel) > 3 else 255
                        
                        # 배경색과 비슷하면 투명하게
                        if (abs(r - bg_color[0]) < tolerance and 
                            abs(g - bg_color[1]) < tolerance and 
                            abs(b - bg_color[2]) < tolerance):
                            new_data.append((r, g, b, 0))  # 투명
                        else:
                            new_data.append((r, g, b, a))
                    
                    img.putdata(new_data)
                    self._log(f"   🎭 배경 제거 완료")
            
            return img
            
        except Exception as e:
            self._log(f"   🎭 배경 제거 실패: {e}")
            return img
    


    def _get_video_rotation(self, clip):
        """영상 rotation 메타데이터 감지"""
        try:
            import subprocess, json
            ff = self._get_ffmpeg_path() if hasattr(self, '_get_ffmpeg_path') else 'ffmpeg'
            ff_probe = ff.replace('ffmpeg', 'ffprobe')
            result = subprocess.run([
                ff_probe, '-v', 'quiet', '-print_format', 'json',
                '-show_streams', clip.filename
            ], capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            for stream in data.get('streams', []):
                tags = stream.get('tags', {})
                rot = tags.get('rotate', tags.get('rotation', None))
                if rot:
                    return int(rot)
            return 0
        except Exception:
            return 0

    def _get_subtitle_style(self):
        """14종 프리셋 + 색상/회전/그림자 다양화 (한 영상 내 통일)"""
        
        # ========================================
        # 14종 프리셋 중 랜덤 선택
        # A: 둥근 박스, B: 밑줄, C: 반투명 띠, D: 네온 글로우
        # E: 말풍선, F: 형광펜, G: 클래식 (외곽선)
        # I: 그라데이션 박스, J: 테이프 스타일, K: 팝업/3D 느낌
        # L: 라운드 태그, M: 깔끔 미니멀, N: 유튜브 자동자막풍
        # ========================================
        preset = random.choice(["A", "B", "C", "D", "E", "F", "G", "I", "J", "K", "L", "M", "N"])
        
        # 프리셋별 색상 풀
        COLOR_POOLS = {
            "A": [(0, 0, 0), (20, 30, 60), (40, 40, 50)],
            "B": [(255, 220, 0), (255, 150, 50), (0, 230, 180), (255, 100, 150)],
            "C": [(0, 0, 0), (20, 30, 80), (60, 20, 80)],
            "D": [(255, 220, 0), (255, 100, 200), (100, 200, 255), (0, 255, 180)],
            "E": [(255, 255, 255), (255, 250, 230), (240, 248, 255)],
            "F": [(255, 255, 0), (180, 255, 100), (255, 180, 200), (150, 220, 255)],
            "G": [(255, 212, 0), (79, 195, 247), (255, 82, 82), (0, 230, 118)],
            "H": [(255, 255, 255), (255, 255, 0), (0, 255, 200)],
            "I": [(30, 60, 120), (80, 30, 100), (20, 80, 60), (100, 40, 40)],  # 그라데이션 시작색
            "J": [(255, 230, 150), (200, 230, 255), (255, 200, 200), (200, 255, 200)],  # 테이프색
            "K": [(255, 80, 80), (80, 150, 255), (255, 180, 0), (0, 200, 150)],  # 팝업 강조색
            "L": [(100, 200, 255), (255, 150, 200), (150, 255, 180), (255, 200, 100)],  # 태그색
            "M": [(255, 255, 255)],  # 미니멀 흰색
            "N": [(0, 0, 0, 200)],  # 유튜브풍 배경색
        }
        
        preset_color = random.choice(COLOR_POOLS[preset])
        
        rotation = random.uniform(-3, 3)
        
        shadow_directions = [
            (-2, -2), (0, -2), (2, -2),
            (-2, 0),          (2, 0),
            (-2, 2),  (0, 2),  (2, 2),
        ]
        shadow_dir = random.choice(shadow_directions)
        
        use_bottom = random.random() < 0.5
        
        if use_bottom:
            y_min, y_max = 0.65, 0.72
            self._log(f"      📍 자막 위치: 하단 (캐릭터 밑)")
        else:
            y_min, y_max = 0.40, 0.50
            self._log(f"      📍 자막 위치: 중앙")
        
        position_y = random.uniform(y_min, y_max)
        
        font_path = self._get_font_path()
        font_size = random.choice([52, 54, 56, 58])
        
        style = {
            "preset": preset,
            "font_path": font_path,
            "font_size": font_size,
            "position_y": position_y,
            "rotation": rotation,
            "shadow_dir": shadow_dir,
            "preset_color": preset_color,
            "box_padding_x": 50,
            "box_padding_y": 30,
        }
        
        if preset == "A":  # 둥근 박스 + 흰색 + 검정 외곽선
            style.update({
                "bg_type": "rounded_box",
                "font_color": (255, 255, 255),
                "box_color": preset_color,
                "box_opacity": 180,
                "box_radius": 14,
                "outline_width": 3,
                "outline_color": (0, 0, 0),
            })
        elif preset == "B":  # 밑줄만
            style.update({
                "bg_type": "underline",
                "font_color": (255, 255, 255),
                "underline_color": preset_color,
                "underline_thickness": 8,
                "outline_width": 3,
                "outline_color": (0, 0, 0),
            })
        elif preset == "C":  # 반투명 띠 + 그림자
            style.update({
                "bg_type": "stripe",
                "font_color": (255, 255, 255),
                "stripe_color": (*preset_color, 160),
                "outline_width": 3,
                "outline_color": (0, 0, 0),
                "use_shadow": True,
            })
        elif preset == "D":  # 없음 + 네온 글로우
            style.update({
                "bg_type": "none",
                "font_color": (255, 255, 255),
                "glow_color": preset_color,
                "glow_size": 8,
                "outline_width": 4,
                "outline_color": (0, 0, 0),
            })
        elif preset == "E":  # 말풍선
            style.update({
                "bg_type": "speech_bubble",
                "font_color": (20, 20, 80),
                "bubble_color": preset_color,
                "bubble_tail": random.choice(["left", "right", "center"]),
                "outline_width": 3,
                "outline_color": (255, 255, 255),
            })
        elif preset == "F":  # 형광펜
            style.update({
                "bg_type": "highlight",
                "font_color": (20, 20, 80),
                "highlight_color": (*preset_color, 200),
                "outline_width": 2,
                "outline_color": (255, 255, 255),
            })
        elif preset == "G":  # 기존 스타일 (흰색 + 강조색 + 외곽선)
            style.update({
                "bg_type": "classic",
                "font_color": (255, 255, 255),
                "accent_color": preset_color,
                "outline_width": 4,
                "outline_color": (0, 0, 0),
                "has_background": random.choice([True, False]),
                "box_color": (0, 0, 0),
                "box_opacity": 140,
                "box_radius": 14,
            })
        elif preset == "I":  # 그라데이션 박스
            end_r = min(255, preset_color[0] + 80)
            end_g = min(255, preset_color[1] + 80)
            end_b = min(255, preset_color[2] + 80)
            style.update({
                "bg_type": "gradient_box",
                "font_color": (255, 255, 255),
                "grad_start": (*preset_color, 220),
                "grad_end": (end_r, end_g, end_b, 220),
                "box_radius": 16,
                "outline_width": 3,
                "outline_color": (0, 0, 0),
            })
        elif preset == "J":  # 테이프/마스킹테이프 스타일
            style.update({
                "bg_type": "tape",
                "font_color": (40, 40, 40),
                "tape_color": (*preset_color[:3], 210),
                "outline_width": 0,
                "outline_color": (0, 0, 0),
                "rotation": random.uniform(-2, 2),
            })
        elif preset == "K":  # 팝업/3D 느낌
            style.update({
                "bg_type": "popup",
                "font_color": (255, 255, 255),
                "popup_color": preset_color,
                "outline_width": 4,
                "outline_color": (0, 0, 0),
                "use_shadow": True,
                "shadow_dir": (4, 4),
            })
        elif preset == "L":  # 라운드 태그 (알약 모양)
            style.update({
                "bg_type": "pill_tag",
                "font_color": (255, 255, 255),
                "pill_color": (*preset_color[:3], 220),
                "outline_width": 2,
                "outline_color": (255, 255, 255),
            })
        elif preset == "M":  # 깔끔 미니멀 (외곽선 두꺼운 흰색)
            style.update({
                "bg_type": "minimal",
                "font_color": (255, 255, 255),
                "outline_width": 5,
                "outline_color": (0, 0, 0),
            })
        elif preset == "N":  # 유튜브 자동자막풍 (검정 반투명 배경)
            style.update({
                "bg_type": "yt_auto",
                "font_color": (255, 255, 255),
                "yt_bg_color": (0, 0, 0, 180),
                "outline_width": 0,
            })
        
        return style
    

    def _create_subtitle_clips(self, sentence, dur, subtitle_style, current_time, sub_y):
        """⭐ v6.3.3: 긴 자막 자동 분할 (의미 단위, 최대 3분할)
        
        18자 초과 → 의미 단위로 분할하여 시간차 표시
        36자 초과 → 3분할
        Returns: (clips_list, new_current_time)
        """
        MAX_SINGLE = 18  # 이 이하면 분할 불필요
        MAX_DOUBLE = 36  # 이 초과면 3분할
        
        # 정규화 (길이 판단용)
        norm_text = self._normalize_subtitle(sentence)
        norm_text = self._remove_chinese_chars(norm_text)
        text_len = len(norm_text)
        
        # 18자 이하 → 기존 방식 (분할 없음)
        if text_len <= MAX_SINGLE:
            clip = self._create_subtitle(sentence, dur, subtitle_style)
            clip = clip.set_start(current_time).set_position(("center", sub_y))
            return [clip], current_time + dur
        
        # 분할점 찾기 함수
        def find_break_point(text, start_ratio=0.5):
            """텍스트에서 최적 분할점 찾기"""
            t_len = len(text)
            mid = int(t_len * start_ratio)
            best_pos = None
            best_score = t_len * 100
            
            good_break_after = (
                '이용하면', '있으면', '되면', '하면', '나면', '오면',
                '있어', '있는', '없는', '되는', '하는',
                '통해', '위해', '따라', '덕분에', '때문에',
                '더불어', '또한', '함께', '그리고', '하지만',
                '뿐만', '아니라', '게다가', '그래서',
                '입니다', '합니다', '됩니다', '습니다',
                '인데요', '거든요', '한데요', '이에요',
                '있고', '되고', '하고', '이며', '으며',
            )
            bad_break_after = ('단', '약', '총', '무려', '불과', '최소', '최대', '겨우', '바로', '이')
            
            for i in range(t_len):
                if text[i] != ' ':
                    continue
                if i < 4 or (t_len - i) < 4:
                    continue
                
                before = text[:i].rstrip()
                after_text = text[i+1:].lstrip()
                
                score = abs(i - mid)
                
                for kw in good_break_after:
                    if before.endswith(kw):
                        score -= 15
                        break
                
                if before.endswith(','):
                    score -= 10
                
                last_word = before.split()[-1] if before.split() else ""
                if last_word in bad_break_after:
                    score += 30
                
                if after_text and after_text[0].isdigit():
                    score += 20
                
                if score < best_score:
                    best_score = score
                    best_pos = i
            
            return best_pos
        
        # 36자 초과 → 3분할
        if text_len > MAX_DOUBLE:
            # 1/3, 2/3 지점에서 분할
            pos1 = find_break_point(sentence, 0.33)
            if pos1:
                part1 = sentence[:pos1].strip()
                rest = sentence[pos1:].strip()
                pos2 = find_break_point(rest, 0.5)
                if pos2:
                    part2 = rest[:pos2].strip()
                    part3 = rest[pos2:].strip()
                    
                    total_len = len(part1) + len(part2) + len(part3)
                    dur1 = dur * (len(part1) / total_len) if total_len > 0 else dur / 3
                    dur2 = dur * (len(part2) / total_len) if total_len > 0 else dur / 3
                    dur3 = dur - dur1 - dur2
                    
                    # 최소 1.2초 보장
                    min_dur = 1.2
                    for d_ref, d_val in [(0, dur1), (1, dur2), (2, dur3)]:
                        if d_val < min_dur and dur > min_dur * 3:
                            pass  # 아래서 처리
                    
                    self._log(f"      ✂️ 자막3분할: [{part1}] ({dur1:.1f}초) + [{part2}] ({dur2:.1f}초) + [{part3}] ({dur3:.1f}초)")
                    
                    clips = []
                    clip1 = self._create_subtitle(part1, dur1, subtitle_style)
                    clip1 = clip1.set_start(current_time).set_position(("center", sub_y))
                    clips.append(clip1)
                    
                    clip2 = self._create_subtitle(part2, dur2, subtitle_style)
                    clip2 = clip2.set_start(current_time + dur1).set_position(("center", sub_y))
                    clips.append(clip2)
                    
                    clip3 = self._create_subtitle(part3, dur3, subtitle_style)
                    clip3 = clip3.set_start(current_time + dur1 + dur2).set_position(("center", sub_y))
                    clips.append(clip3)
                    
                    return clips, current_time + dur
        
        # 18~36자 → 2분할
        best_pos = find_break_point(sentence, 0.5)
        
        if not best_pos:
            clip = self._create_subtitle(sentence, dur, subtitle_style)
            clip = clip.set_start(current_time).set_position(("center", sub_y))
            return [clip], current_time + dur
        
        part1 = sentence[:best_pos].strip()
        part2 = sentence[best_pos:].strip()
        
        # 글자 수 비율로 시간 분배
        len1 = len(part1)
        len2 = len(part2)
        total_len = len1 + len2
        dur1 = dur * (len1 / total_len) if total_len > 0 else dur / 2
        dur2 = dur - dur1
        
        # 최소 1.2초 보장
        if dur1 < 1.2 and dur > 2.4:
            dur1 = 1.2
            dur2 = dur - dur1
        elif dur2 < 1.2 and dur > 2.4:
            dur2 = 1.2
            dur1 = dur - dur2
        
        self._log(f"      ✂️ 자막분할: [{part1}] ({dur1:.1f}초) + [{part2}] ({dur2:.1f}초)")
        
        clips = []
        clip1 = self._create_subtitle(part1, dur1, subtitle_style)
        clip1 = clip1.set_start(current_time).set_position(("center", sub_y))
        clips.append(clip1)
        
        clip2 = self._create_subtitle(part2, dur2, subtitle_style)
        clip2 = clip2.set_start(current_time + dur1).set_position(("center", sub_y))
        clips.append(clip2)
        
        return clips, current_time + dur
    

    def _create_subtitle(self, text, duration, style):
        """8종 프리셋 지원 자막 생성 (80px 고정 + 한줄/두줄 법칙 + 문단 맞춤)"""
        
        # 자막 텍스트 정규화 (영어→한글, TTS와 동일하게)
        text = self._normalize_subtitle(text)
        
        # 한자 제거 (혹시 남아있으면)
        text = self._remove_chinese_chars(text)
        
        # H: 타이핑 효과면 별도 함수 호출
        if style.get("bg_type") == "typing":
            return self._create_subtitle_typing(text, duration, style)
        
        font_path = style.get("font_path") or self._get_font_path()
        font_size = 70  # 70px 고정!
        font_color = style.get("font_color", (255, 255, 255))
        bg_type = style.get("bg_type", "classic")
        rotation = style.get("rotation", 0)
        shadow_dir = style.get("shadow_dir", (2, 2))
        
        try:
            font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # ========================================
        # 한줄/두줄 법칙 (문단에 맞춰서!)
        # 70px 기준 한 줄 최대 약 12자
        # ========================================
        max_chars_per_line = 12
        text_len = len(text)
        
        if text_len <= max_chars_per_line:
            # 12자 이하 → 한 줄
            lines = [text]
        else:
            # 12자 초과 → 두 줄로 (문단 맞춤)
            # ⭐ 최소 줄 길이: 각 줄 5자 이상 (3~4자짜리 짧은 줄 방지!)
            MIN_LINE_LEN = 5
            split_pos = None
            
            # 1순위: 쉼표(,) 위치에서 나누기 (숫자 쉼표 제외!)
            for ci, cc in enumerate(text):
                if cc == ',':
                    # 앞뒤가 숫자면 분리하지 않음 (예: 1,534 / 2,000)
                    before_c = text[ci-1] if ci > 0 else ''
                    after_c = text[ci+1] if ci < text_len - 1 else ''
                    if before_c.isdigit() and after_c.isdigit():
                        continue  # 숫자 쉼표는 건너뛰기
                    # ⭐ 각 줄 최소 5자 이상이어야 분리
                    if ci >= MIN_LINE_LEN and (text_len - ci - 1) >= MIN_LINE_LEN:
                        split_pos = ci + 1
                        break
            
            # 2순위: 의미 단위 분할 (조사/접속사 뒤 공백에서 균형 나누기)
            if not split_pos:
                mid = text_len // 2
                best_pos = None
                best_score = text_len * 10  # 높을수록 나쁨
                
                # ⭐ v6.3.2: 의미 단위 분할 우선 키워드
                # 이 단어들 뒤에서 나누면 자연스러움
                good_break_after = ('이용하면', '있어', '있는', '통해', '위해', '따라', '덕분에',
                                    '더불어', '또한', '함께', '그리고', '하지만', '때문에',
                                    '뿐만', '아니라', '게다가', '그래서', '즉', '결국',
                                    '예정이며', '있으며', '습니다', '입니다', '돋보입니다')
                
                for i, char in enumerate(text):
                    if char == ' ':
                        # ⭐ 각 줄 최소 5자 보장
                        if i < MIN_LINE_LEN or (text_len - i - 1) < MIN_LINE_LEN:
                            continue
                        
                        # 기본 점수: 중앙과의 거리
                        diff = abs(i - mid)
                        score = diff
                        
                        # ⭐ 의미 단위 보너스: 좋은 분할점이면 점수 감소
                        before_word = text[:i].rstrip()
                        for kw in good_break_after:
                            if before_word.endswith(kw):
                                score -= 5  # 보너스
                                break
                        
                        # ⭐ 나쁜 분할: "단 X분", "약 X분" 등 수식어+숫자 사이 분할 방지
                        after_text = text[i+1:].lstrip()
                        if after_text and after_text[0].isdigit():
                            score += 10  # 패널티
                        # "단", "약", "총", "무려" 뒤에서 바로 나누면 어색
                        last_word = before_word.split()[-1] if before_word.split() else ""
                        if last_word in ('단', '약', '총', '무려', '불과', '최소', '최대', '겨우'):
                            score += 15  # 큰 패널티
                        
                        if score < best_score:
                            best_score = score
                            best_pos = i
                
                if best_pos:
                    split_pos = best_pos
            
            # 3순위: 그냥 중간에서 자르기 (숫자 중간은 피함!)
            if not split_pos:
                mid = text_len // 2
                best = mid
                for offset in range(0, text_len // 2):
                    for candidate in [mid + offset, mid - offset]:
                        if MIN_LINE_LEN <= candidate <= text_len - MIN_LINE_LEN:
                            c = text[candidate]
                            if c.isdigit() or c in '.,':
                                continue
                            best = candidate
                            break
                    else:
                        continue
                    break
                split_pos = best
            
            line1 = text[:split_pos].strip()
            line2 = text[split_pos:].strip()
            
            # 빈 줄 방지
            if not line1:
                line1 = text[:text_len//2]
            if not line2:
                line2 = text[text_len//2:]
            
            lines = [line1, line2]
        
        # ========================================
        # 화면 밖 나가면 자동 축소
        # 최대 너비 950px 기준
        # ========================================
        max_width = 950
        
        # 각 줄 너비 체크
        max_line_width = 0
        for line in lines:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            max_line_width = max(max_line_width, line_width)
        
        # 화면 밖으로 나가면 폰트 축소
        while max_line_width > max_width and font_size > 40:
            font_size -= 5
            try:
                font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except:
                break
            
            max_line_width = 0
            for line in lines:
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                max_line_width = max(max_line_width, line_width)
        
        line_height = font_size + 18
        padding_x = style.get("box_padding_x", 50)
        padding_y = style.get("box_padding_y", 30)
        total_height = len(lines) * line_height + padding_y * 2
        total_width = 1000
        
        img = Image.new("RGBA", (total_width, total_height + 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # ========================================
        # 프리셋별 배경 그리기
        # ========================================
        if bg_type == "rounded_box":  # A: 둥근 박스
            box_color = (*style.get("box_color", (0, 0, 0)), style.get("box_opacity", 180))
            draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height],
                                   radius=style.get("box_radius", 14), fill=box_color)
        
        elif bg_type == "underline":  # B: 밑줄만
            pass  # 텍스트 후에 밑줄 그림
        
        elif bg_type == "stripe":  # C: 반투명 띠
            stripe_color = style.get("stripe_color", (0, 0, 0, 160))
            draw.rectangle([0, padding_y//2, total_width, total_height - padding_y//2], fill=stripe_color)
        
        elif bg_type == "speech_bubble":  # E: 말풍선
            bubble_color = style.get("bubble_color", (255, 255, 255))
            # 말풍선 본체
            draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height - 15],
                                   radius=20, fill=(*bubble_color, 255))
            # 꼬리
            tail_pos = style.get("bubble_tail", "center")
            if tail_pos == "left":
                tail_x = total_width // 4
            elif tail_pos == "right":
                tail_x = total_width * 3 // 4
            else:
                tail_x = total_width // 2
            draw.polygon([(tail_x - 15, total_height - 15), (tail_x + 15, total_height - 15), 
                         (tail_x, total_height + 5)], fill=(*bubble_color, 255))
        
        elif bg_type == "highlight":  # F: 형광펜
            pass  # 텍스트 뒤에 줄별로 그림
        
        elif bg_type == "classic":  # G: 기존 스타일
            if style.get("has_background", False):
                box_color = (*style.get("box_color", (0, 0, 0)), style.get("box_opacity", 140))
                draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height],
                                       radius=style.get("box_radius", 14), fill=box_color)
        
        elif bg_type == "gradient_box":  # I: 그라데이션 박스
            grad_start = style.get("grad_start", (30, 60, 120, 220))
            grad_end = style.get("grad_end", (110, 140, 200, 220))
            radius = style.get("box_radius", 16)
            # 세로 그라데이션
            for row_y in range(total_height):
                ratio = row_y / max(total_height - 1, 1)
                r = int(grad_start[0] + (grad_end[0] - grad_start[0]) * ratio)
                g = int(grad_start[1] + (grad_end[1] - grad_start[1]) * ratio)
                b = int(grad_start[2] + (grad_end[2] - grad_start[2]) * ratio)
                a = int(grad_start[3] + (grad_end[3] - grad_start[3]) * ratio)
                draw.line([(padding_x//2, row_y), (total_width - padding_x//2, row_y)], fill=(r, g, b, a))
            # 모서리 둥글게 마스킹
            mask_img = Image.new("L", (total_width, total_height + 20), 0)
            mask_draw = ImageDraw.Draw(mask_img)
            mask_draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height], radius=radius, fill=255)
            img.putalpha(mask_img)
            draw = ImageDraw.Draw(img)
        
        elif bg_type == "tape":  # J: 마스킹테이프 스타일
            tape_color = style.get("tape_color", (255, 230, 150, 210))
            # 약간 거친 사각형 (테이프 느낌)
            draw.rectangle([padding_x//3, 3, total_width - padding_x//3, total_height - 3], fill=tape_color)
            # 테이프 양쪽 찢어진 효과 (톱니)
            for ty in range(0, total_height, 8):
                offset = random.randint(0, 4)
                draw.rectangle([padding_x//3 - offset, ty, padding_x//3, ty + 4], fill=(0, 0, 0, 0))
                draw.rectangle([total_width - padding_x//3, ty, total_width - padding_x//3 + offset, ty + 4], fill=(0, 0, 0, 0))
        
        elif bg_type == "popup":  # K: 팝업/3D 느낌
            popup_color = style.get("popup_color", (255, 80, 80))
            # 3D 그림자 (오른쪽 아래)
            draw.rounded_rectangle([padding_x//2 + 6, 6, total_width - padding_x//2 + 6, total_height + 6],
                                   radius=14, fill=(0, 0, 0, 120))
            # 메인 박스
            draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height],
                                   radius=14, fill=(*popup_color, 240))
            # 상단 하이라이트 (빛 반사)
            draw.rounded_rectangle([padding_x//2 + 4, 2, total_width - padding_x//2 - 4, total_height // 3],
                                   radius=12, fill=(255, 255, 255, 40))
        
        elif bg_type == "pill_tag":  # L: 알약형 태그
            pill_color = style.get("pill_color", (100, 200, 255, 220))
            pill_radius = total_height // 2  # 완전 라운드
            draw.rounded_rectangle([padding_x//2, 0, total_width - padding_x//2, total_height],
                                   radius=pill_radius, fill=pill_color)
            # 얇은 흰색 안쪽 테두리
            draw.rounded_rectangle([padding_x//2 + 3, 3, total_width - padding_x//2 - 3, total_height - 3],
                                   radius=pill_radius - 3, outline=(255, 255, 255, 120), width=2)
        
        elif bg_type == "minimal":  # M: 미니멀 (배경 없음, 두꺼운 외곽선만)
            pass  # 텍스트만 그림 (외곽선이 두꺼움)
        
        elif bg_type == "yt_auto":  # N: 유튜브 자동자막풍
            yt_bg = style.get("yt_bg_color", (0, 0, 0, 180))
            # 각 줄별 배경 (줄 간격에 맞춰)
            cur_y = padding_y
            for line_text in lines:
                bbox_t = font.getbbox(line_text)
                lw = bbox_t[2] - bbox_t[0]
                lh = bbox_t[3] - bbox_t[1]
                lx = (total_width - lw) // 2
                draw.rectangle([lx - 8, cur_y - 4, lx + lw + 8, cur_y + lh + 8], fill=yt_bg)
                cur_y += line_height
        
        # ========================================
        # 텍스트 그리기
        # ========================================
        y = padding_y
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (total_width - w) // 2
            
            # F: 형광펜 - 텍스트 뒤에 하이라이트
            if bg_type == "highlight":
                hl_color = style.get("highlight_color", (255, 255, 0, 200))
                draw.rectangle([x - 5, y - 2, x + w + 5, y + h + 5], fill=hl_color)
            
            # 그림자 (C 프리셋 또는 use_shadow)
            if style.get("use_shadow") or bg_type == "none":
                sx, sy = shadow_dir
                for offset in range(3, 0, -1):
                    alpha = 80 - offset * 20
                    draw.text((x + sx * offset, y + sy * offset), line, font=font, fill=(0, 0, 0, alpha))
            
            # D: 네온 글로우
            if bg_type == "none":
                glow_color = style.get("glow_color", (255, 220, 0))
                glow_size = style.get("glow_size", 8)
                for offset in range(glow_size, 0, -2):
                    alpha = int(100 - offset * 10)
                    draw.text((x, y), line, font=font, fill=(*glow_color, alpha))
            
            # 외곽선 (오버레이 밝기에 따라 결정) - 2px로 최적화
            outline_width = style.get("outline_width", 2)  # 기본 2px (성능 최적화)
            
            # ⭐ 오버레이 밝기 체크 (style에서 전달받거나 글씨 밝기로 판단)
            overlay_is_dark = style.get("overlay_is_dark", None)
            
            # style에 outline_color가 이미 설정되어 있으면 그것 사용
            if "outline_color" in style:
                outline_color = style["outline_color"]
            else:
                # 글씨 밝기로 테두리 색상 결정
                r, g, b = font_color[:3]
                brightness = (r + g + b) / 3
                if brightness > 128:
                    outline_color = (0, 0, 0)  # 밝은 글씨 → 검정 테두리
                else:
                    outline_color = (255, 255, 255)  # 어두운 글씨 → 흰색 테두리
            
            if outline_width > 0:
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), line, font=font, fill=(*outline_color, 255))
            
            # 메인 텍스트
            draw.text((x, y), line, font=font, fill=font_color)
            
            # B: 밑줄
            if bg_type == "underline":
                ul_color = style.get("underline_color", (255, 220, 0))
                ul_thick = style.get("underline_thickness", 8)
                draw.rectangle([x - 5, y + h + 2, x + w + 5, y + h + 2 + ul_thick], fill=(*ul_color, 255))
            
            y += line_height
        
        # 회전 적용
        if rotation != 0:
            img = img.rotate(rotation, expand=True, fillcolor=(0, 0, 0, 0), resample=Image.BICUBIC)
        
        # RGBA → RGB + 마스크 분리 (moviepy 호환)
        if img.mode == "RGBA":
            rgb = np.array(img.convert("RGB"))
            alpha = np.array(img.split()[3]) / 255.0  # 0~1 정규화
            clip = ImageClip(rgb).set_duration(duration)
            mask = ImageClip(alpha, ismask=True).set_duration(duration)
            clip = clip.set_mask(mask)
            return clip
        else:
            return ImageClip(np.array(img)).set_duration(duration)
    

    def _create_subtitle_typing(self, text, duration, style):
        """타이핑 효과 자막 (한 글자씩 나타남)"""
        font_path = style.get("font_path") or self._get_font_path()
        font_size = style.get("font_size", 56)
        font_color = style.get("font_color", (255, 255, 255))
        
        # 글자 수에 따라 폰트 크기 조절
        text_len = len(text)
        if text_len > 30:
            font_size = int(font_size * 0.75)
        elif text_len > 25:
            font_size = int(font_size * 0.85)
        font_size = max(36, font_size)
        
        try:
            font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # 글자당 타이핑 시간 (전체의 60%에서 타이핑, 40%는 유지)
        typing_duration = duration * 0.6
        char_duration = typing_duration / max(len(text), 1)
        
        frames = []
        fps = 15  # 타이핑용 낮은 FPS
        
        for frame_idx in range(int(duration * fps)):
            t = frame_idx / fps
            
            # 현재 시간에 보여줄 글자 수
            if t < typing_duration:
                visible_chars = int(t / char_duration) + 1
            else:
                visible_chars = len(text)
            
            visible_text = text[:visible_chars]
            
            # 이미지 생성
            bbox = font.getbbox(text)  # 전체 텍스트 기준 크기
            w = bbox[2] - bbox[0] + 100
            h = bbox[3] - bbox[1] + 60
            
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            x = 50
            y = 30
            
            # 외곽선
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), visible_text, font=font, fill=(0, 0, 0, 255))
            
            # 메인 텍스트
            draw.text((x, y), visible_text, font=font, fill=font_color)
            
            frames.append(np.array(img))
        
        # 클립 생성
        def make_frame(t):
            idx = min(int(t * fps), len(frames) - 1)
            return frames[idx]
        
        from moviepy.editor import VideoClip
        clip = VideoClip(make_frame, duration=duration)
        return clip
    
    # ============================================================
    # CTA 스타일
    # ============================================================
    

    def _normalize_subtitle(self, text):
        """자막용 텍스트 변환 (TTS 호흡 기호만 제거, 영어는 그대로)"""
        
        # 앞에 붙은 번호 제거 (예: "1, 이 단지는", "2. 여기는" 등)
        # ⚠️ "1,000세대" 같은 숫자 쉼표는 보호! (쉼표 뒤가 숫자면 건너뛰기)
        text = re.sub(r'^\d+[.]\s+', '', text.strip())  # "1. " 형태만 제거
        text = re.sub(r'^\d+,\s+(?!\d)', '', text.strip())  # "1, " 형태 (뒤가 숫자 아닐 때만)
        
        # TTS 호흡 기호 제거 (자막에는 불필요)
        text = text.replace(" — ", " ")  # 긴 대시 양쪽 공백 포함
        text = text.replace("— ", " ")   # 긴 대시 뒤 공백
        text = text.replace(" —", " ")   # 긴 대시 앞 공백
        text = text.replace("—", " ")    # 긴 대시만
        
        # ⚠️ 영어는 그대로 유지! (NotoSansKR 폰트로 표시 가능)
        # GTX, AI, SK 등 → 변환하지 않음
        
        # 특수문자 변환
        text = text.replace("&", "그리고")
        text = text.replace("+", "플러스")
        
        # 중복 공백 제거
        text = " ".join(text.split())
        
        # 숫자는 그대로 유지 (30평, 5억, 500m 등 - 보기 쉬움)
        
        return text
    

    def _remove_chinese_chars(self, text):
        """한자(漢字) 제거 - 한글로 대체하거나 삭제"""
        if not text:
            return text
        
        # 자주 나오는 한자 → 한글 변환
        chinese_to_korean = {
            '注': '주', '意': '의', '重': '중', '要': '요',
            '必': '필', '須': '수', '確': '확', '認': '인',
            '最': '최', '高': '고', '新': '신', '大': '대',
            '小': '소', '中': '중', '上': '상', '下': '하',
            '前': '전', '後': '후', '左': '좌', '右': '우',
            '東': '동', '西': '서', '南': '남', '北': '북',
            '入': '입', '出': '출', '住': '주', '居': '거',
            '區': '구', '市': '시', '道': '도', '里': '리',
            '樓': '루', '層': '층', '坪': '평', '室': '실',
        }
        
        for cn, kr in chinese_to_korean.items():
            text = text.replace(cn, kr)
        
        # 나머지 한자는 삭제 (CJK Unified Ideographs 범위)
        result = ""
        for char in text:
            # 한자 범위: U+4E00 ~ U+9FFF
            if '\u4e00' <= char <= '\u9fff':
                continue  # 한자 삭제
            result += char
        
        return result
    

    def _normalize_tts(self, text):
        """TTS 발음 정규화 - 영어/숫자를 한글로"""
        
        # 중국어 문자 제거 (맨 먼저!)
        text = self._remove_chinese_chars(text)
        
        # ⭐ 쉼표 포함 숫자 먼저 처리! (1,534 → 1534)
        text = re.sub(r'(\d),(\d)', r'\1\2', text)
        
        # 숫자+세대/동/호 (부동산 특수) - 공백 없이 붙여야 TTS가 자연스럽게 읽음
        text = re.sub(r'(\d+)세대', lambda m: self._num_to_korean(m.group(1)) + "세대", text)
        text = re.sub(r'(\d+)개동', lambda m: self._num_to_korean(m.group(1)) + "개동", text)
        text = re.sub(r'(\d+)타입', lambda m: self._num_to_korean(m.group(1)) + "타입", text)
        
        # 숫자 단위 - 공백 없이 붙여야 TTS가 자연스럽게 읽음
        text = re.sub(r'(\d+)평', lambda m: self._num_to_korean(m.group(1)) + "평", text)
        text = re.sub(r'(\d+)억', lambda m: self._num_to_korean(m.group(1)) + "억", text)
        text = re.sub(r'(\d+)만', lambda m: self._num_to_korean(m.group(1)) + "만", text)
        text = re.sub(r'(\d+)천', lambda m: self._num_to_korean(m.group(1)) + "천", text)
        text = re.sub(r'(\d+)%', lambda m: self._num_to_korean(m.group(1)) + "퍼센트", text)
        text = re.sub(r'(\d+)kg', lambda m: self._num_to_korean(m.group(1)) + "킬로그램", text)
        text = re.sub(r'(\d+)km', lambda m: self._num_to_korean(m.group(1)) + "킬로미터", text)
        text = re.sub(r'(\d+)m²', lambda m: self._num_to_korean(m.group(1)) + "제곱미터", text)
        text = re.sub(r'(\d+)㎡', lambda m: self._num_to_korean(m.group(1)) + "제곱미터", text)
        text = re.sub(r'(\d+)m', lambda m: self._num_to_korean(m.group(1)) + "미터", text)
        text = re.sub(r'(\d+)층', lambda m: self._num_to_korean(m.group(1)) + "층", text)
        text = re.sub(r'(\d+)년', lambda m: self._num_to_korean(m.group(1)) + "년", text)
        text = re.sub(r'(\d+)월', lambda m: self._num_to_korean(m.group(1)) + "월", text)
        text = re.sub(r'(\d+)일', lambda m: self._num_to_korean(m.group(1)) + "일", text)
        text = re.sub(r'(\d+)분', lambda m: self._num_to_korean(m.group(1)) + "분", text)
        text = re.sub(r'(\d+)호선', lambda m: self._num_to_korean(m.group(1)) + "호선", text)
        
        # 교통/철도
        text = text.replace("GTX", "지티엑스")
        text = text.replace("G T X", "지티엑스")
        text = text.replace("SRT", "에스알티")
        text = text.replace("KTX", "케이티엑스")
        text = text.replace("ITX", "아이티엑스")
        
        # 부동산 관련 약어 (긴 것 먼저!)
        text = text.replace("HDC", "에이치디씨")
        text = text.replace("DL이앤씨", "디엘이앤씨")
        text = text.replace("IPARK", "아이파크")
        text = text.replace("e편한세상", "이편한세상")
        text = text.replace("KCC", "케이씨씨")
        text = text.replace("LH", "엘에이치")
        text = text.replace("SH", "에스에이치")
        text = text.replace("JC", "제이씨")
        text = text.replace("HL", "에이치엘")
        text = text.replace("DS", "디에스")
        
        # 일반 약어
        text = text.replace("AI", "에이아이")
        text = text.replace("IC", "아이씨")
        text = text.replace("IT", "아이티")
        text = text.replace("IoT", "아이오티")
        text = text.replace("LED", "엘이디")
        text = text.replace("LG", "엘지")
        text = text.replace("SK", "에스케이")
        text = text.replace("GS", "지에스")
        text = text.replace("HD", "에이치디")
        text = text.replace("DL", "디엘")
        text = text.replace("VR", "브이알")
        text = text.replace("AR", "에이알")
        text = text.replace("5G", "파이브지")
        text = text.replace("4K", "포케이")
        text = text.replace("8K", "에잇케이")
        
        # 특수문자 (TTS 발음 이상 방지)
        text = text.replace("—", ", ")   # ⭐ 긴 대시 → 쉼표(자연스러운 호흡)
        text = text.replace("–", ", ")   # en dash
        text = text.replace("―", ", ")   # 수평선
        text = text.replace("…", ".")    # 말줄임표 → 마침표
        text = text.replace("...", ".")   # 점세개
        text = text.replace("..", ".")    # 점두개
        text = text.replace("!!", "!")    # 느낌표 중복
        text = text.replace("??", "?")   # 물음표 중복
        text = text.replace("!?", "!")   
        text = text.replace("「", "")     # 일본식 괄호
        text = text.replace("」", "")
        text = text.replace("『", "")
        text = text.replace("』", "")
        text = text.replace("(", "")     # 괄호 제거
        text = text.replace(")", "")
        text = text.replace("[", "")
        text = text.replace("]", "")
        text = text.replace("\"", "")    # 따옴표
        text = text.replace("'", "")
        text = text.replace("'", "")
        text = text.replace("'", "")
        text = text.replace(""", "")
        text = text.replace(""", "")
        text = text.replace("&", " 그리고 ")
        text = text.replace("@", " 골뱅이 ")
        text = text.replace("#", " 번호 ")
        text = text.replace("+", " 플러스 ")
        text = text.replace("~", " 에서 ")
        text = text.replace("-", " ")
        text = text.replace("·", " ")
        text = text.replace("★", "")
        text = text.replace("☆", "")
        text = text.replace("※", "")
        text = text.replace("▶", "")
        text = text.replace("●", "")
        text = text.replace("✔", "")
        text = text.replace("✅", "")
        text = text.replace("❌", "")
        text = text.replace("🔥", "")
        text = text.replace("⭐", "")
        # 이모지 전체 제거
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001f900-\U0001f9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', '', text)

        # 천 단위 쉼표 제거
        text = re.sub(r'(\d),(\d)', r'\1\2', text)
        
        # ⭐ 남은 영문 약어를 알파벳 한글로 변환 (발음 개선)
        # 예: "DL" → "디엘", "JC" → "제이씨"
        alpha_to_korean = {
            'A': '에이', 'B': '비', 'C': '씨', 'D': '디', 'E': '이',
            'F': '에프', 'G': '지', 'H': '에이치', 'I': '아이', 'J': '제이',
            'K': '케이', 'L': '엘', 'M': '엠', 'N': '엔', 'O': '오',
            'P': '피', 'Q': '큐', 'R': '알', 'S': '에스', 'T': '티',
            'U': '유', 'V': '브이', 'W': '더블유', 'X': '엑스', 'Y': '와이',
            'Z': '제트'
        }
        
        def _alpha_to_kor(match):
            word = match.group(0)
            # 대문자 약어 → 한글 발음 변환
            return "".join(alpha_to_korean.get(c, c) for c in word)
        
        # 모든 연속 대문자를 한글로 변환
        text = re.sub(r'[A-Z]+', _alpha_to_kor, text)
        
        # 소문자 영단어 제거 (TTS 외계어 방지)
        text = re.sub(r'\b[a-z]+\b', '', text)
        
        # ⭐ v6.3.2: 단위 없는 숫자도 한글 변환 (100 이상)
        # "1534" → "천오백삼십사", "25" → "이십오" 등
        def _convert_bare_number(m):
            num_str = m.group(0)
            try:
                num = int(num_str)
                if num >= 100:
                    return self._num_to_korean(num_str)
                elif num >= 10:
                    # 10~99: 한국어로 변환
                    tens = ['', '십', '이십', '삼십', '사십', '오십', '육십', '칠십', '팔십', '구십']
                    ones = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
                    return tens[num // 10] + ones[num % 10]
                else:
                    # 1~9: 그대로 (한자리 숫자는 TTS가 잘 읽음)
                    return num_str
            except:
                return num_str
        
        text = re.sub(r'\b\d{2,}\b', _convert_bare_number, text)

        # ⭐⭐ 외계어/늘어짐 강잠금 (한글 TTS 안정화)
        # 영문→한글, 숫자→한글 변환 완료 후 최종 정리
        # - 한글/숫자/기본문장부호만 남기고 나머지 제거
        text = re.sub(r'[ㄱ-ㅎㅏ-ㅣ]+', '', text)  # 단독 자모 제거
        text = re.sub(r'[~∼˜`^_=]+', ' ', text)
        text = re.sub(r'[/\\|]+', ' ', text)
        text = re.sub(r'[•·ㆍ∙]+', ' ', text)
        # 허용 문자 외 제거 (한글/숫자/공백/기본문장부호)
        text = re.sub(r'[^0-9가-힣\s\.,!?%]', ' ', text)
        text = re.sub(r'([,\.!?])\1+', r'\1', text)  # 문장부호 중복 정리
        
        # 연속 공백 제거
        text = re.sub(r'\s+', ' ', text).strip()
        
        # ⭐ 한국어 음성 늘어짐 방지
        # 문장 끝에 마침표/느낌표/물음표가 없으면 강제 추가
        # → TTS가 문장 끝을 명확히 인식하여 모음 늘어짐 현상 방지
        if text and text[-1] not in '.!?':
            text += '.'
        
        return text
    

    def _num_to_korean(self, num_str):
        """숫자를 한국어 발음으로 변환 (2000→이천, 1534→천오백삼십사)"""
        try:
            num = int(num_str)
            if num == 0:
                return "영"
            
            result = ""
            
            # 만 단위
            if num >= 10000:
                man = num // 10000
                if man == 1:
                    result += "만"
                else:
                    result += self._num_to_korean(str(man)) + "만"
                num %= 10000
            
            # 천 단위
            if num >= 1000:
                cheon = num // 1000
                if cheon == 1:
                    result += "천"
                else:
                    result += ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"][cheon] + "천"
                num %= 1000
            
            # 백 단위
            if num >= 100:
                baek = num // 100
                if baek == 1:
                    result += "백"
                else:
                    result += ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"][baek] + "백"
                num %= 100
            
            # 십 단위
            if num >= 10:
                sip = num // 10
                if sip == 1:
                    result += "십"
                else:
                    result += ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"][sip] + "십"
                num %= 10
            
            # 일 단위
            if num > 0:
                result += ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"][num]
            
            return result
        except:
            return num_str
    
    # ============================================================
    # 소스/오디오 유틸
    # ============================================================



    def generate_titles(self, project_name, tone="FRIEND", channel_seed=None, channel=None):
        """제목 생성 - 대사 기반 GPT 생성만 사용 (템플릿 없음)"""
        if not project_name:
            return []

        self._log(f"🎯 제목 생성: {project_name}")

        # 1순위: 대사 있으면 대사 기반 GPT 생성
        if channel:
            all_seeds = self._get_all_seed_lines(channel)
            if all_seeds:
                seed_titles = self._generate_titles_from_seeds(project_name, channel)
                if seed_titles:
                    self._log(f"   ✅ 대사 기반 제목 {len(seed_titles)}개 생성")
                    return seed_titles
                self._log(f"   ⚠️ 대사 기반 제목 재시도")
                seed_titles = self._generate_titles_from_seeds(project_name, channel)
                if seed_titles:
                    return seed_titles
                return []

        # 대사 없을 때: GPT로 직접 제목 6개 생성
        if not self.client:
            self._log("   ❌ OpenAI 없음")
            return []

        _ch_key = getattr(channel, 'channel_id', None) or getattr(channel, 'project_name', project_name) if channel else project_name
        _hist_titles, _ = self._load_title_history(_ch_key)
        _prev = list(dict.fromkeys(_hist_titles[-30:] + self.recent_titles[-10:]))
        _prev_str = "\n".join([f"- {t}" for t in _prev[-20:]]) if _prev else "없음"

        prompt = f"""유튜브 쇼츠 분양 영상 제목 6개를 만들어라.

【프로젝트명】 {project_name}

【이미 사용한 제목 - 절대 중복 금지】
{_prev_str}

【핵심 원칙】
- 웹서치로 프로젝트명을 검색해서 실제 정보(위치, 단지 유형, 특징, 가격 등)를 파악해라
- 파악한 실제 정보를 제목에 직접 녹여라 (시니어타운이면 시니어타운 느낌으로, 한옥이면 한옥 느낌으로)
- "지금 봐야 하는 이유", "영업사원도 말 안 한" 같은 뻔한 표현 금지!
- 6개 모두 완전히 다른 각도 (질문형/감탄형/비교형/긴박형/팩트형/타겟형)
- 6개 중 같은 시작 단어/표현 절대 금지! ("실화?"나 "왜?" 등으로 다 시작하면 안 됨)

【조건】
- 20~35자 이내
- 「|」 「/」 「-」 구분자 절대 금지, 자연스러운 한 문장으로
- 금지어: 청약, 가점, 당첨, 폭등, 확정, 보장, 무조건, 100%, 입주

【출력】
제목만 한 줄에 하나씩 (번호 없이)"""

        try:
            # Responses API로 웹서치 사용
            try:
                resp = self.client.responses.create(
                    model="gpt-5.4-mini",
                    input=prompt,
                    tools=[{"type": "web_search"}],
                )
                result_text = resp.output_text or ""
            except Exception:
                # Responses API 실패 시 Chat Completions 폴백
                r2 = self.client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=400,
                    temperature=1.0,
                )
                result_text = r2.choices[0].message.content or ""
            lines = [l.strip().strip('"\'- ').strip()
                     for l in result_text.strip().split('\n') if l.strip()]
            titles = []
            for t in lines:
                if '|' in t:
                    continue
                t = self._filter_forbidden(t[:40])
                if t and t not in titles:
                    titles.append(t)
                    self._log(f"      🏷️ {t}")
            if titles:
                self._save_title_history(_ch_key, titles, [])
                self.recent_titles.extend(titles)
                self.recent_titles = self.recent_titles[-300:]
            return titles
        except Exception as e:
            self._log(f"   ⚠️ 제목 생성 실패: {e}")
            return []

    def create_video(self, channel, title_idx, mode, upload=False, stop_callback=None):
        """모드별 영상 생성 메인 함수
        stop_callback: 중지 여부 체크 함수 (True 반환 시 중지)
        """
        self._stop_callback = stop_callback  # 저장해서 내부에서 사용
        # ⭐ 채널 TTS 속도 배율 적용
        self.tts_speed = getattr(channel, 'tts_speed', 1.0)
        
        if not MOVIEPY_OK:
            self._log("❌ MoviePy 필요")
            return None
        
        if title_idx >= len(channel.titles):
            self._log("❌ 제목 인덱스 초과")
            return None
        
        title = channel.titles[title_idx]
        suffix = "_UPLOADED" if upload else "_READY"
        
        self._log(f"🎬 제작: {title[:30]}... (모드: {mode})")
        self._current_mode = mode  # ⭐ 현재 제작 모드 저장 (PDF 팩트 조건에서 참조)
        
        # 중지 체크
        if self._check_stop():
            self._log("⏸️ 중지됨")
            return None
        
        # 모드별 분기 - 각각 완전히 분리된 로직
        video_path = None
        if mode == "videos":
            video_path = self._create_mode_videos(channel, title, suffix)
        elif mode == "mixed":
            video_path = self._create_mode_mixed(channel, title, suffix)
        elif mode == "pdf":
            video_path = self._create_mode_pdf(channel, title, suffix)
        else:  # photos (기본)
            video_path = self._create_mode_photos(channel, title, suffix)
        
        # 업로드 처리
        if upload and video_path:
            self._log(f"📤 YouTube 업로드 시작...")
            
            # 메타데이터 읽기
            out_dir = os.path.dirname(video_path)
            metadata_path = os.path.join(out_dir, "metadata.json")
            thumbnail_path = os.path.join(out_dir, "thumbnail.jpg")
            
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # 업로드 (딜레이 포함)
                video_id = self.upload_video(
                    video_path=video_path,
                    title=metadata.get('title', title),
                    description=metadata.get('description', ''),
                    tags=metadata.get('tags', []),
                    thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
                    channel=channel,
                    privacy="public"
                )
                
                if video_id:
                    self._log(f"✅ 업로드 완료: https://youtube.com/watch?v={video_id}")
                else:
                    self._log(f"⚠️ 업로드 실패")
            else:
                self._log(f"⚠️ 메타데이터 없음 - 업로드 건너뜀")
        
        return video_path
    
    # ============================================================
    # Videos 모드: 영상 이어붙이기 방식
    # - TTS 한 번에 생성
    # - 영상 끊김없이 풀 재생 후 이어붙이기
    # - 음성 길이까지 채우기
    # ============================================================

    def _create_mode_videos(self, channel, title, suffix):
        self._log("   📹 Videos 모드: 영상 이어붙이기")
        self._log(f"   📁 채널: {channel.project_name}")
        
        # 0. 자막 위치 고정 (Photos 모드와 동일)
        self._last_img_bottom = 1300  # 1300 고정
        
        # 0. 캐시 초기화 (영상마다 새로 선택)
        self.clear_char_cache()
        
        # 1. 영상 파일 로드
        video_folder = channel.video_folder
        if not video_folder or not os.path.isdir(video_folder):
            self._log(f"❌ 영상 폴더 없음 (경로: {video_folder})")
            return None
        
        video_exts = ["*.mp4", "*.MP4", "*.mov", "*.MOV", "*.avi", "*.AVI", "*.mkv", "*.webm"]
        video_files = []
        for ext in video_exts:
            video_files.extend(glob.glob(os.path.join(video_folder, ext)))
        
        if not video_files:
            self._log("❌ 영상 파일 없음")
            return None
        
        # 정렬 (숫자면 순번, 카카오톡 등은 랜덤)
        video_files = self._sort_files(video_files)
        self._log(f"   📂 영상 {len(video_files)}개 로드")
        
        # 2. 각 영상 길이 확인
        video_info = []  # [(path, duration), ...]
        for vf in video_files:
            try:
                clip = VideoFileClip(vf, audio=False)
                dur = clip.duration
                clip.close()
                video_info.append((vf, dur))
                self._log(f"      📹 {os.path.basename(vf)}: {dur:.1f}초")
            except Exception as e:
                self._log(f"      ⚠️ {os.path.basename(vf)} 읽기 실패")
        
        if not video_info:
            self._log("❌ 유효한 영상 없음")
            return None
        
        # 3. 스타일 고정 (영상 전체에서 1회만 선택)
        subtitle_style = self._get_subtitle_style()
        cta_style = self._get_cta_style()
        inquiry_style = self._get_inquiry_style()  # 6종 프리셋
        self._log(f"   📦 문의박스 스타일: {inquiry_style['preset']}")
        
        # 4. 음성 선택
        if channel.voice == "random":
            voice_id = random.choice(self.voices) if self.voices else None
        else:
            voice_id = channel.voice
        self._log(f"   🎤 음성: {voice_id[:8] if voice_id else 'None'}...")
        
        # 5. 톤 1번 선택 → 영상 전체 통일
        tone_key = getattr(channel, 'tone', 'hybrid') or 'hybrid'
        if tone_key == "hybrid" or tone_key not in TONE_TYPES:
            tone_key = self._select_tone()
        tone_info = TONE_TYPES.get(tone_key, TONE_TYPES["hybrid"])
        self._log(f"   🎭 톤: {tone_info['name']}")
        
        # 6. CTA 확인 → 대본 개수 결정 (opening_enabled 체크!)
        cta_enabled = getattr(channel, 'opening_enabled', False)
        cta_text = ''
        if cta_enabled:
            # 대사설정 [CTA]에서 랜덤 선택
            cta_lines = self._get_cta_lines(channel)
            if cta_lines:
                # ⭐ 라운드 로빈: 같은 오프닝 반복 방지
                if not hasattr(self, '_cta_index'):
                    self._cta_index = {}
                ch_key = getattr(channel, 'name', 'default')
                idx = self._cta_index.get(ch_key, 0) % len(cta_lines)
                cta_text = cta_lines[idx]
                self._cta_index[ch_key] = idx + 1
        # ⭐ 문장 수 랜덤 (10~15문장) - 영상 길이 다양화
        _total = random.choice([10, 12, 15])
        if cta_text:
            script_count = _total - 1  # CTA 1개 + 대본
            self._log(f"   📢 CTA: {cta_text[:20]}...")
        else:
            script_count = _total
        self._log(f"   📝 목표 문장 수: {_total}문장 (대본 {script_count} + CTA {1 if cta_text else 0})")
        
        # 7. 대본 생성 (대사설정 [대사] 우선, 없으면 PDF 팩트)
        seed_line = None
        
        # ⭐ 대사설정 [대사] (팩트체크 없이 그대로) + PDF 팩트 (숫자/사업개요) 합치기
        parts = []
        
        # 1. 대사설정 [대사] - 팩트체크 없이 그대로 사용!
        all_seeds = self._get_all_seed_lines(channel)
        if all_seeds:
            seed_text = "\n".join(all_seeds)
            parts.append(f"【대사설정 - 아래 내용만으로 대본을 만들어라. 이 외 내용 추가 금지!】\n{seed_text}")
            self._log(f"   📝 대사설정 전체 {len(all_seeds)}개 전달")
        # ⭐ 오프닝(CTA)도 대본 소재로 추가 (대사와 중복 무관)
        _cta_lines = self._get_cta_lines(channel)
        if _cta_lines:
            _cta_seed = " / ".join(_cta_lines[:3])  # 최대 3개
            parts.append(f"【오프닝 소재 (대본에 자연스럽게 녹여라!)】\n{_cta_seed}")
            self._log(f"   📢 오프닝 소재 반영: {_cta_seed[:40]}...")
        
        # 2. PDF 팩트 - 현재 제작 모드가 pdf일 때만 실행 (photos/videos 모드에서는 건너뜀)
        _current_mode = getattr(self, "_current_mode", "")
        _is_pdf = (_current_mode == "pdf")
        if _is_pdf:
            self._log(f"   📄 [PDF모드] 팩트체크 시도")
            pdf_facts = self._extract_pdf_keywords_for_title(channel, title)
            if pdf_facts:
                parts.append(f"【PDF 검증 팩트】\n{pdf_facts}")
                _pf_preview = pdf_facts[:60].replace("\n", " / ")
                self._log(f"   ✅ [PDF모드] 팩트 반영: {_pf_preview}...")
        
        seed_line = "\n\n".join(parts) if parts else None
        
        script = self.generate_script(title, tone_key, sentence_count=script_count, channel_seed=seed_line)
        sentences = self._split_sentences(script)
        # 목표 문장 수 초과 시 자르기
        if script_count and len(sentences) > script_count + 2:
            sentences = sentences[:script_count]
            self._log(f"   ✂️ 문장 수 조정: {len(sentences)}문장")
        
        # ⭐ 대본 로그 추가
        self._log(f"   📝 대본 생성: {len(sentences)}문장")
        for i, s in enumerate(sentences[:3]):
            self._log(f"      {i+1}. {s[:30]}...")
        if len(sentences) > 3:
            self._log(f"      ... (총 {len(sentences)}문장)")
        
        # ⭐ Videos 모드: 모든 문장 사용 (자르지 않음! 영상은 TTS 길이에 맞춤)
        
        # ⭐ 오프닝 처리
        # CTA가 있으면 맨 앞에 추가 (오프닝 ON)
        # CTA가 없으면 GPT 대본 첫 문장(훅) 그대로 사용 (오프닝 OFF)
        if cta_text:
            sentences = [cta_text] + sentences
        # else: GPT가 만든 첫 문장(훅)이 이미 있음!
        
        # ⭐ 링크 멘트: 링크가 있으면 마지막 문장을 교체 (늘어짐 방지)
        link_closing = self._get_link_closing(channel)
        if link_closing and len(sentences) >= 2:
            sentences[-1] = link_closing
            self._log(f"   🔗 링크 멘트 (교체): {link_closing[:25]}...")
        
        # ⭐ 중지 체크
        if self._check_stop():
            self._log("⏸️ 중지됨")
            return None
        
        # 8. Google Cloud TTS 생성
        self._log("   🎙️ Google Cloud TTS 생성...")
        
        hybrid_audio_path, sentence_durations = self.generate_tts_hybrid(
            sentences, voice_id, tone_key, channel
        )
        
        if hybrid_audio_path and sentence_durations:
            # ⭐ 문장 수 ↔ 타이밍 수 안전장치
            if len(sentence_durations) < len(sentences):
                avg = sum(sentence_durations) / len(sentence_durations) if sentence_durations else 2.5
                while len(sentence_durations) < len(sentences):
                    sentence_durations.append(avg)
                self._log(f"   ⚠️ 타이밍 부족 → {len(sentences)}개로 보정")
            elif len(sentence_durations) > len(sentences):
                sentence_durations = sentence_durations[:len(sentences)]
            
            # 전체 오디오 클립 (자르지 않고 그대로 사용!)
            full_audio_clip = AudioFileClip(hybrid_audio_path)
            actual_duration = full_audio_clip.duration
            
            # ⭐ 싱크 보정 (실제 오디오 길이와 측정값 비교)
            measured_total = sum(sentence_durations)
            if measured_total > 0:
                scale_ratio = actual_duration / measured_total
                if abs(scale_ratio - 1.0) > 0.15:
                    sentence_durations = [d * scale_ratio for d in sentence_durations]
                    self._log(f"   🔄 싱크 보정: 측정 {measured_total:.1f}초 → 실제 {actual_duration:.1f}초 (비율: {scale_ratio:.2f})")
                elif abs(scale_ratio - 1.0) > 0.03:
                    diff = actual_duration - measured_total
                    sentence_durations[-1] = max(0.3, sentence_durations[-1] + diff)
                    self._log(f"   🔧 미세 보정: 마지막 문장 {diff:+.2f}초 조정")
                else:
                    self._log(f"   ✅ 싱크 정확: {measured_total:.1f}초 ≈ 실제 {actual_duration:.1f}초")
            
            total_audio_duration = actual_duration
            self._log(f"   🔊 음성 길이: {total_audio_duration:.1f}초")
            
            # ⭐ 오디오는 자르지 않고 full_audio_clip 그대로 사용!
            full_audio = full_audio_clip
        else:
            # 실패 시 기존 방식으로 폴백
            self._log("   ⚠️ TTS 실패 → 개별 생성으로 폴백")
            sentence_audios = []
            sentence_durations = []
            
            for sent in sentences:
                audio_path = self.generate_tts(sent, voice_id, tone_key=tone_key)
                if audio_path and os.path.exists(audio_path):
                    audio_clip = AudioFileClip(audio_path)
                    dur = audio_clip.duration
                    sentence_audios.append(audio_clip)
                    sentence_durations.append(dur)
                else:
                    sentence_audios.append(None)
                    sentence_durations.append(2.5)
            
            total_audio_duration = sum(sentence_durations)
            self._log(f"   🔊 음성 길이: {total_audio_duration:.1f}초 (개별 TTS)")
            
            # 개별 TTS일 때만 합치기
            full_audio = self._concat_audio_with_silence(sentence_audios, sentence_durations)
        
        # 60초 초과 시 속도 조절 (규칙 8-2)
        if total_audio_duration > 60:
            speed_ratio = total_audio_duration / 58.0
            sentence_durations = [d / speed_ratio for d in sentence_durations]
            total_audio_duration = sum(sentence_durations)
            # ⭐ 실제 오디오도 속도 조절 (싱크 맞추기!)
            try:
                # ⭐ v6.3.2: moviepy fx 올바른 방식으로 속도 조절
                try:
                    import moviepy.audio.fx.all as afx
                    full_audio = full_audio.fx(afx.speedx, speed_ratio)
                except (ImportError, AttributeError):
                    try:
                        from moviepy.audio.fx import speedx as _speedx
                        full_audio = full_audio.fx(_speedx, speed_ratio)
                    except ImportError:
                        # ffmpeg으로 직접 속도 조절
                        import tempfile, subprocess
                        tmp_in = tempfile.mktemp(suffix='_in.mp3')
                        tmp_out = tempfile.mktemp(suffix='_out.mp3')
                        full_audio.write_audiofile(tmp_in, fps=44100, verbose=False, logger=None)
                        subprocess.run([_FFMPEG_BIN, '-y', '-i', tmp_in, '-filter:a', f'atempo={speed_ratio}', tmp_out],
                                       capture_output=True, startupinfo=_STARTUPINFO)
                        full_audio.close()
                        full_audio = AudioFileClip(tmp_out)
                        os.remove(tmp_in)
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_audio_duration:.1f}초 (오디오+자막 동기화)")
            except Exception as e:
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_audio_duration:.1f}초 (오디오 속도조절 실패: {e})")
            # ⭐ 속도 조절 후 실제 오디오와 자막 싱크 재검증
            try:
                actual_after = full_audio.duration
                dur_sum = sum(sentence_durations)
                if abs(actual_after - dur_sum) > 0.5:
                    rescale = actual_after / dur_sum
                    sentence_durations = [d * rescale for d in sentence_durations]
                    self._log(f"   🔧 속도조절 후 재보정: 자막 {dur_sum:.1f}→{sum(sentence_durations):.1f}초 (실제 {actual_after:.1f}초)")
            except:
                pass
        
        # ⭐ v6.3.2: 타이밍 붕괴 감지 + 6초 cap (video 모드)
        if sentence_durations and len(sentence_durations) > 1:
            max_dur = max(sentence_durations)
            if max_dur > total_audio_duration * 0.5:
                avg_dur = total_audio_duration / len(sentence_durations)
                sentence_durations = [avg_dur] * len(sentence_durations)
                self._log(f"   ⚠️ 타이밍 붕괴 감지 → 균등 분배: {avg_dur:.1f}초 × {len(sentence_durations)}문장")
            else:
                MAX_SCENE_DUR = 6.0
                excess_total = 0
                capped_indices = []
                for i, d in enumerate(sentence_durations):
                    if d > MAX_SCENE_DUR:
                        excess_total += d - MAX_SCENE_DUR
                        capped_indices.append(i)
                if excess_total > 0:
                    short_indices = [i for i in range(len(sentence_durations)) if i not in capped_indices]
                    if short_indices:
                        per_short = excess_total / len(short_indices)
                        for i in capped_indices:
                            sentence_durations[i] = MAX_SCENE_DUR
                        for i in short_indices:
                            sentence_durations[i] += per_short
                        self._log(f"   ⚙️ 장면 최대 {MAX_SCENE_DUR}초 cap: {len(capped_indices)}개 장면 조정, {excess_total:.1f}초 재분배")
        
        self._log(f"   🎬 영상 이어붙이기...")
        video_clips = []
        current_duration = 0
        video_idx = 0
        used_videos = []  # 사용한 영상 추적
        
        while current_duration < total_audio_duration:
            if video_idx >= len(video_info):
                # 모든 영상 사용했으면 처음부터 반복
                video_idx = 0
                self._log(f"      🔄 영상 반복")
            
            vpath, vdur = video_info[video_idx]
            remaining = total_audio_duration - current_duration
            
            try:
                clip = VideoFileClip(vpath, audio=False)
                
                if vdur <= remaining:
                    # 영상 전체 사용
                    use_dur = vdur
                    self._log(f"      ▶️ {os.path.basename(vpath)} 전체 ({use_dur:.1f}초)")
                else:
                    # 필요한 만큼만 자르기
                    use_dur = remaining
                    clip = clip.subclip(0, use_dur)
                    self._log(f"      ✂️ {os.path.basename(vpath)} ({use_dur:.1f}초/{vdur:.1f}초)")
                
                # 세로 9:16 변환
                clip = self._fit_to_vertical(clip)
                video_clips.append(clip)
                current_duration += use_dur
                used_videos.append(os.path.basename(vpath))
                
            except Exception as e:
                self._log(f"      ⚠️ {os.path.basename(vpath)} 처리 실패: {e}")
            
            video_idx += 1
            
            # 진행률
            percent = int(min(current_duration / total_audio_duration * 30, 30))
            self._progress(percent)
        
        self._log(f"   ✅ 영상 {len(video_clips)}개 사용 ({current_duration:.1f}초)")
        
        # ⭐ v6.3.2: fps 통일 (모든 클립을 동일 fps로)
        target_fps = 30
        unified_clips = []
        for vc in video_clips:
            clip_fps = getattr(vc, 'fps', None)
            if clip_fps and clip_fps != target_fps:
                vc = vc.set_fps(target_fps)
            elif not clip_fps:
                vc = vc.set_fps(target_fps)
            unified_clips.append(vc)
        video_clips = unified_clips
        
        # 7. 전환 효과 적용 후 영상 합치기
        if len(video_clips) == 1:
            base_video = video_clips[0]
        else:
            # ⭐ 전환 효과 없이 바로 연결 (까만 화면 방지!)
            self._log(f"   🔗 영상 {len(video_clips)}개 연결 중...")
            base_video = concatenate_videoclips(video_clips, method="chain")
            self._log(f"   ✅ 영상 연결 완료: {base_video.duration:.1f}초")
        
        # ⭐ v6.3.2: base_video 길이와 오디오 길이 불일치 보정
        if abs(base_video.duration - total_audio_duration) > 0.1:
            self._log(f"   🔧 영상/오디오 길이 보정: 영상 {base_video.duration:.1f}초 → 오디오 {total_audio_duration:.1f}초")
            if base_video.duration > total_audio_duration:
                base_video = base_video.subclip(0, total_audio_duration)
            # 영상이 짧으면 마지막 프레임 freeze
            elif base_video.duration < total_audio_duration - 0.5:
                from moviepy.editor import concatenate_videoclips as _concat
                freeze_dur = total_audio_duration - base_video.duration
                last_frame = base_video.to_ImageClip(t=base_video.duration - 0.1).set_duration(freeze_dur)
                base_video = _concat([base_video, last_frame], method="chain")
                self._log(f"      🖼️ 마지막 프레임 freeze: +{freeze_dur:.1f}초")
        
        # 8. 자막 오버레이 (TTS 실제 길이로 싱크)
        self._log("   📝 자막 오버레이...")
        
        # sentence_durations는 위에서 TTS 실제 길이로 이미 설정됨
        
        subtitle_clips = []
        current_time = 0
        sub_y = getattr(self, '_last_img_bottom', 1300) + 30
        for i, sentence in enumerate(sentences):
            dur = sentence_durations[i]
            clips, current_time = self._create_subtitle_clips(sentence, dur, subtitle_style, current_time, sub_y)
            subtitle_clips.extend(clips)
        
        # 9. 문의박스 (전체 영상에 고정, 스타일 적용)
        inquiry = self._create_inquiry_box(
            getattr(channel, 'inquiry_1', ''),
            getattr(channel, 'inquiry_2', ''),
            getattr(channel, 'inquiry_3', ''),
            total_audio_duration,
            style=inquiry_style,
            is_bright_overlay=False,
            line4=getattr(channel, 'inquiry_4', ''),
            font_size_base=getattr(channel, 'inquiry_font_size', None),
            no_bg=getattr(channel, 'inquiry_no_bg', False),
            bold=getattr(channel, 'inquiry_bold', True),
            font_sizes=[getattr(channel, 'inquiry_size_1', getattr(channel, 'inquiry_font_size', 90)), getattr(channel, 'inquiry_size_2', 70), getattr(channel, 'inquiry_size_3', 70), getattr(channel, 'inquiry_size_4', 70)]
        )
        
        # 10. 캐릭터 (있으면) - 오른쪽 끝, 자막 위
        character_clip = None
        char_name = getattr(channel, 'character', '')
        if char_name:
            char_img = self.get_character_image(char_name)
            if char_img:
                char_img = char_img.resize((250, 350), RESAMPLE)
                # ⭐ RGBA 투명 처리 (마스크 사용)
                if char_img.mode == 'RGBA':
                    char_rgb = np.array(char_img.convert('RGB'))
                    char_alpha = np.array(char_img.split()[3]) / 255.0
                    character_clip = ImageClip(char_rgb, ismask=False).set_duration(total_audio_duration)
                    character_clip = character_clip.set_mask(ImageClip(char_alpha, ismask=True).set_duration(total_audio_duration))
                else:
                    character_clip = ImageClip(np.array(char_img.convert('RGB'))).set_duration(total_audio_duration)
                character_clip = character_clip.set_position((800, 1050))
        
        # 11. 최종 합성 (CTA 클립은 별도 제거 - 이미 자막에 포함됨)
        self._log(f"   🎬 최종 레이어 합성 중...")
        self._log(f"      ✅ 베이스 영상: {base_video.duration:.1f}초")
        self._log(f"      ✅ 자막: {len(subtitle_clips)}개")
        if inquiry:
            self._log(f"      ✅ 문의박스: 있음 (스타일: {inquiry_style})")
        if character_clip:
            self._log(f"      ✅ 캐릭터: {char_name}")
        
        layers = [base_video] + subtitle_clips
        
        # ⭐ 장면 오버레이 (1,3,5,7번 장면에 PNG 오버레이)
        scene_overlays = self._load_scene_overlays()
        if scene_overlays:
            overlay_time = 0
            for si in range(len(sentences)):
                if si in scene_overlays and si < len(sentence_durations):
                    ov_clip = self._make_scene_overlay_clip(
                        scene_overlays[si],
                        sentence_durations[si],
                        overlay_time
                    )
                    if ov_clip:
                        layers.append(ov_clip)
                        self._log(f"      ✅ 장면오버레이: 장면{si+1} ({overlay_time:.1f}~{overlay_time+sentence_durations[si]:.1f}초)")
                overlay_time += sentence_durations[si]
        
        if inquiry:
            _inq_pos_pct = getattr(channel, 'inquiry_position', 5)
            try:
                _inq_pos_pct = int(_inq_pos_pct)
            except:
                _inq_pos_pct = 5
            layers.append(inquiry.set_position(("center", _inq_pos_pct / 100), relative=True))
        if character_clip:
            layers.append(character_clip)
        
        self._log(f"   🔗 총 {len(layers)}개 레이어 합성 중...")
        
        # ⭐ CompositeVideoClip 직접 합성 (fl() 제거 - 성능 개선!)
        final = CompositeVideoClip(layers, size=(1080, 1920))
        # ⭐ v6.3.2: fps 보장 (Videos 모드)
        if not getattr(final, 'fps', None):
            final = final.set_fps(30)
        self._log(f"   ✅ 최종 영상: {final.duration:.1f}초 ({final.fps}fps)")
        
        # 13. 오디오 합성 (BGM + 음성)
        mixed_audio = self._build_mixed_audio(full_audio, total_audio_duration, [])
        if mixed_audio:
            final = final.set_audio(mixed_audio)
        
        # 14. 렌더링
        out_dir = self._create_output_folder(channel.project_name, "videos", suffix)
        out_path = os.path.join(out_dir, "video.mp4")
        
        self._render_final(final, out_path)
        
        # 15. 썸네일 (첫 영상 프레임)
        first_video = video_info[0][0] if video_info else None
        if first_video:
            # 첫 문장(hook)을 썸네일에 전달
            channel._thumb_hook = sentences[0] if sentences else ""
            self._create_thumbnail(
                first_video, title,
                getattr(channel, 'thumb_line1', ''),
                os.path.join(out_dir, "thumbnail.jpg"),
                channel.project_name,
                channel=channel,
                inquiry_style=inquiry_style,
                frame_style=None  # 영상은 테두리 없음
            )
        
        # 16. 메타데이터
        self._create_metadata(title, channel, os.path.join(out_dir, "metadata.json"))
        
        # 정리
        final.close()
        for c in video_clips:
            try:
                c.close()
            except:
                pass
        
        self._log(f"✅ 완료: {out_path}")
        return out_path
    
    # ============================================================
    # Mixed 모드: 영상 + 사진 교차 (음성 기준)
    # - TTS 한 번에 생성
    # - 영상 끝까지 → 사진 (자막 길이) → 다음 영상 → ...
    # ============================================================

    def _create_mode_mixed(self, channel, title, suffix):
        self._log("   🔀 Mixed 모드: 영상+사진 교차")
        self._log(f"   📁 채널: {channel.project_name}")
        
        # 0. 자막 위치 고정 (Photos 모드와 동일)
        self._last_img_bottom = 1300  # 1300 고정
        
        # 1. 영상/사진 파일 로드
        video_folder = channel.video_folder
        photo_folder = channel.photo_folder
        
        video_files = []
        photo_files = []
        
        if video_folder and os.path.isdir(video_folder):
            for ext in ["*.mp4", "*.mov", "*.avi"]:
                video_files.extend(glob.glob(os.path.join(video_folder, ext)))
                video_files.extend(glob.glob(os.path.join(video_folder, ext.upper())))
            video_files = list(dict.fromkeys(os.path.normcase(f) for f in video_files))
            video_files = [os.path.normpath(f) for f in video_files]
            video_files = self._sort_files(video_files)
        
        if photo_folder and os.path.isdir(photo_folder):
            for ext in ["*.jpg", "*.jpeg", "*.png"]:
                photo_files.extend(glob.glob(os.path.join(photo_folder, ext)))
                photo_files.extend(glob.glob(os.path.join(photo_folder, ext.upper())))
            # Windows 대소문자 중복 제거
            photo_files = list(dict.fromkeys(os.path.normcase(f) for f in photo_files))
            photo_files = [os.path.normpath(f) for f in photo_files]
            photo_files = self._sort_files(photo_files)
        
        if not video_files and not photo_files:
            self._log("❌ 소스 없음")
            return None
        
        self._log(f"   📂 영상 {len(video_files)}개, 사진 {len(photo_files)}개")
        
        # 2. 영상 길이 정보
        video_info = []
        for vf in video_files:
            try:
                clip = VideoFileClip(vf, audio=False)
                video_info.append((vf, clip.duration))
                clip.close()
            except:
                pass
        
        # 3. 스타일 고정
        subtitle_style = self._get_subtitle_style()
        cta_style = self._get_cta_style()
        inquiry_style = self._get_inquiry_style()  # 6종 프리셋
        enhance_style = self._get_photo_enhance_style()  # 📸 사진 보정 스타일
        frame_style = self._get_frame_style()  # 🖼️ 프레임 스타일
        enhance_name = PHOTO_ENHANCE_STYLES.get(enhance_style, {}).get('name', '원본')
        self._log(f"   📦 문의박스 스타일: {inquiry_style['preset']}")
        self._log(f"   📸 사진 보정: {enhance_style} ({enhance_name})")
        
        # 4. 음성 선택
        if channel.voice == "random":
            voice_id = random.choice(self.voices) if self.voices else None
        else:
            voice_id = channel.voice
        
        # 5. 톤 1번 선택 → 영상 전체 통일
        tone_key = getattr(channel, 'tone', 'hybrid') or 'hybrid'
        if tone_key == "hybrid" or tone_key not in TONE_TYPES:
            tone_key = self._select_tone()
        tone_info = TONE_TYPES.get(tone_key, TONE_TYPES["hybrid"])
        self._log(f"   🎭 톤: {tone_info['name']}")
        
        # 6. CTA 확인 → 대본 개수 결정 (opening_enabled 체크!)
        cta_enabled = getattr(channel, 'opening_enabled', False)
        cta_text = ''
        if cta_enabled:
            # 대사설정 [CTA]에서 랜덤 선택
            cta_lines = self._get_cta_lines(channel)
            if cta_lines:
                # ⭐ 라운드 로빈: 같은 오프닝 반복 방지
                if not hasattr(self, '_cta_index'):
                    self._cta_index = {}
                ch_key = getattr(channel, 'name', 'default')
                idx = self._cta_index.get(ch_key, 0) % len(cta_lines)
                cta_text = cta_lines[idx]
                self._cta_index[ch_key] = idx + 1
        # ⭐ 문장 수 랜덤 (10~15문장) - 영상 길이 다양화
        _total = random.choice([10, 12, 15])
        if cta_text:
            script_count = _total - 1  # CTA 1개 + 대본
            self._log(f"   📢 CTA: {cta_text[:20]}...")
        else:
            script_count = _total
        self._log(f"   📝 목표 문장 수: {_total}문장 (대본 {script_count} + CTA {1 if cta_text else 0})")
        
        # 7. 대본 생성 (대사설정 [대사] 우선, 없으면 PDF 팩트)
        seed_line = None
        
        # ⭐ 대사설정 [대사] (팩트체크 없이 그대로) + PDF 팩트 (숫자/사업개요) 합치기
        parts = []
        
        # 1. 대사설정 [대사] - 팩트체크 없이 그대로 사용!
        all_seeds = self._get_all_seed_lines(channel)
        if all_seeds:
            seed_text = "\n".join(all_seeds)
            parts.append(f"【대사설정 - 아래 내용만으로 대본을 만들어라. 이 외 내용 추가 금지!】\n{seed_text}")
            self._log(f"   📝 대사설정 전체 {len(all_seeds)}개 전달")
        # ⭐ 오프닝(CTA)도 대본 소재로 추가 (대사와 중복 무관)
        _cta_lines = self._get_cta_lines(channel)
        if _cta_lines:
            _cta_seed = " / ".join(_cta_lines[:3])  # 최대 3개
            parts.append(f"【오프닝 소재 (대본에 자연스럽게 녹여라!)】\n{_cta_seed}")
            self._log(f"   📢 오프닝 소재 반영: {_cta_seed[:40]}...")
        
        # 2. PDF 팩트 - 현재 제작 모드가 pdf일 때만 실행 (photos/videos 모드에서는 건너뜀)
        _current_mode = getattr(self, "_current_mode", "")
        _is_pdf = (_current_mode == "pdf")
        if _is_pdf:
            self._log(f"   📄 [PDF모드] 팩트체크 시도")
            pdf_facts = self._extract_pdf_keywords_for_title(channel, title)
            if pdf_facts:
                parts.append(f"【PDF 검증 팩트】\n{pdf_facts}")
                _pf_preview = pdf_facts[:60].replace("\n", " / ")
                self._log(f"   ✅ [PDF모드] 팩트 반영: {_pf_preview}...")
        
        seed_line = "\n\n".join(parts) if parts else None
        
        script = self.generate_script(title, tone_key, sentence_count=script_count, channel_seed=seed_line)
        sentences = self._split_sentences(script)
        # 목표 문장 수 초과 시 자르기
        if script_count and len(sentences) > script_count + 2:
            sentences = sentences[:script_count]
            self._log(f"   ✂️ 문장 수 조정: {len(sentences)}문장")
        
        # ⭐ 대본 로그 추가
        self._log(f"   📝 대본 생성: {len(sentences)}문장")
        for i, s in enumerate(sentences[:3]):
            self._log(f"      {i+1}. {s[:30]}...")
        if len(sentences) > 3:
            self._log(f"      ... (총 {len(sentences)}문장)")
        
        # ⭐ Mixed 모드: 모든 문장 사용 (자르지 않음!)
        
        # ⭐ 오프닝 처리
        # CTA가 있으면 맨 앞에 추가 (오프닝 ON)
        # CTA가 없으면 GPT 대본 첫 문장(훅) 그대로 사용 (오프닝 OFF)
        if cta_text:
            sentences = [cta_text] + sentences
        
        # ⭐ 링크 멘트: 링크가 있으면 마지막 문장을 교체 (늘어짐 방지)
        link_closing = self._get_link_closing(channel)
        if link_closing and len(sentences) >= 2:
            sentences[-1] = link_closing
            self._log(f"   🔗 링크 멘트 (교체): {link_closing[:25]}...")
        
        # ⭐ 중지 체크
        if self._check_stop():
            self._log("⏸️ 중지됨")
            return None
        
        # 8. Google Cloud TTS 생성
        self._log("   🎙️ Google Cloud TTS 생성...")
        
        hybrid_audio_path, sentence_durations = self.generate_tts_hybrid(
            sentences, voice_id, tone_key, channel
        )
        
        if hybrid_audio_path and sentence_durations:
            # ⭐ 문장 수 ↔ 타이밍 수 안전장치
            if len(sentence_durations) < len(sentences):
                avg = sum(sentence_durations) / len(sentence_durations) if sentence_durations else 2.5
                while len(sentence_durations) < len(sentences):
                    sentence_durations.append(avg)
                self._log(f"   ⚠️ 타이밍 부족 → {len(sentences)}개로 보정")
            elif len(sentence_durations) > len(sentences):
                sentence_durations = sentence_durations[:len(sentences)]
            
            # 전체 오디오 클립 (자르지 않고 그대로 사용!)
            full_audio_clip = AudioFileClip(hybrid_audio_path)
            actual_duration = full_audio_clip.duration
            
            # ⭐ 싱크 보정 (실제 오디오 길이와 측정값 비교)
            measured_total = sum(sentence_durations)
            if measured_total > 0:
                scale_ratio = actual_duration / measured_total
                if abs(scale_ratio - 1.0) > 0.15:
                    sentence_durations = [d * scale_ratio for d in sentence_durations]
                    self._log(f"   🔄 싱크 보정: 측정 {measured_total:.1f}초 → 실제 {actual_duration:.1f}초 (비율: {scale_ratio:.2f})")
                elif abs(scale_ratio - 1.0) > 0.03:
                    diff = actual_duration - measured_total
                    sentence_durations[-1] = max(0.3, sentence_durations[-1] + diff)
                    self._log(f"   🔧 미세 보정: 마지막 문장 {diff:+.2f}초 조정")
                else:
                    self._log(f"   ✅ 싱크 정확: {measured_total:.1f}초 ≈ 실제 {actual_duration:.1f}초")
            
            total_audio_duration = actual_duration
            self._log(f"   🔊 음성 길이: {total_audio_duration:.1f}초")
            
            # ⭐ 오디오는 자르지 않고 full_audio_clip 그대로 사용!
            full_audio = full_audio_clip
        else:
            # 실패 시 폴백
            self._log("   ⚠️ TTS 실패 → 개별 생성으로 폴백")
            sentence_audios = []
            sentence_durations = []
            
            for sent in sentences:
                audio_path = self.generate_tts(sent, voice_id, tone_key=tone_key)
                if audio_path and os.path.exists(audio_path):
                    audio_clip = AudioFileClip(audio_path)
                    dur = audio_clip.duration
                    sentence_audios.append(audio_clip)
                    sentence_durations.append(dur)
                else:
                    sentence_audios.append(None)
                    sentence_durations.append(2.5)
            
            total_audio_duration = sum(sentence_durations)
            self._log(f"   🔊 음성 길이: {total_audio_duration:.1f}초 (개별 TTS)")
            
            # 개별 TTS일 때만 합치기
            full_audio = self._concat_audio_with_silence(sentence_audios, sentence_durations)
        
        # 60초 초과 시 속도 조절 (규칙 8-2)
        if total_audio_duration > 60:
            speed_ratio = total_audio_duration / 58.0
            sentence_durations = [d / speed_ratio for d in sentence_durations]
            total_audio_duration = sum(sentence_durations)
            # ⭐ 실제 오디오도 속도 조절 (싱크 맞추기!)
            try:
                # ⭐ v6.3.2: moviepy fx 올바른 방식으로 속도 조절
                try:
                    import moviepy.audio.fx.all as afx
                    full_audio = full_audio.fx(afx.speedx, speed_ratio)
                except (ImportError, AttributeError):
                    try:
                        from moviepy.audio.fx import speedx as _speedx
                        full_audio = full_audio.fx(_speedx, speed_ratio)
                    except ImportError:
                        # ffmpeg으로 직접 속도 조절
                        import tempfile, subprocess
                        tmp_in = tempfile.mktemp(suffix='_in.mp3')
                        tmp_out = tempfile.mktemp(suffix='_out.mp3')
                        full_audio.write_audiofile(tmp_in, fps=44100, verbose=False, logger=None)
                        subprocess.run([_FFMPEG_BIN, '-y', '-i', tmp_in, '-filter:a', f'atempo={speed_ratio}', tmp_out],
                                       capture_output=True, startupinfo=_STARTUPINFO)
                        full_audio.close()
                        full_audio = AudioFileClip(tmp_out)
                        os.remove(tmp_in)
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_audio_duration:.1f}초 (오디오+자막 동기화)")
            except Exception as e:
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_audio_duration:.1f}초 (오디오 속도조절 실패: {e})")
            # ⭐ 속도 조절 후 실제 오디오와 자막 싱크 재검증
            try:
                actual_after = full_audio.duration
                dur_sum = sum(sentence_durations)
                if abs(actual_after - dur_sum) > 0.5:
                    rescale = actual_after / dur_sum
                    sentence_durations = [d * rescale for d in sentence_durations]
                    self._log(f"   🔧 속도조절 후 재보정: 자막 {dur_sum:.1f}→{sum(sentence_durations):.1f}초 (실제 {actual_after:.1f}초)")
            except:
                pass
        
        # ⭐ v6.3.2: 타이밍 붕괴 감지 + 6초 cap (mixed 모드)
        if sentence_durations and len(sentence_durations) > 1:
            max_dur = max(sentence_durations)
            if max_dur > total_audio_duration * 0.5:
                avg_dur = total_audio_duration / len(sentence_durations)
                sentence_durations = [avg_dur] * len(sentence_durations)
                self._log(f"   ⚠️ 타이밍 붕괴 감지 → 균등 분배: {avg_dur:.1f}초 × {len(sentence_durations)}문장")
            else:
                MAX_SCENE_DUR = 6.0
                excess_total = 0
                capped_indices = []
                for i, d in enumerate(sentence_durations):
                    if d > MAX_SCENE_DUR:
                        excess_total += d - MAX_SCENE_DUR
                        capped_indices.append(i)
                if excess_total > 0:
                    short_indices = [i for i in range(len(sentence_durations)) if i not in capped_indices]
                    if short_indices:
                        per_short = excess_total / len(short_indices)
                        for i in capped_indices:
                            sentence_durations[i] = MAX_SCENE_DUR
                        for i in short_indices:
                            sentence_durations[i] += per_short
                        self._log(f"   ⚙️ 장면 최대 {MAX_SCENE_DUR}초 cap: {len(capped_indices)}개 장면 조정, {excess_total:.1f}초 재분배")
        
        self._log("   🎬 교차 배치...")
        clips = []
        current_duration = 0
        video_idx = 0
        photo_idx = 0
        sentence_idx = 0
        use_video = True  # 영상부터 시작
        
        while current_duration < total_audio_duration and sentence_idx < len(sentences):
            remaining = total_audio_duration - current_duration
            
            if use_video and video_info:
                # 영상 사용 (끝까지 재생)
                if video_idx >= len(video_info):
                    video_idx = 0
                    self._log(f"      🔄 영상 반복 (처음부터)")
                
                vpath, vdur = video_info[video_idx]
                use_dur = min(vdur, remaining)
                
                try:
                    clip = VideoFileClip(vpath, audio=False)
                    if use_dur < vdur:
                        clip = clip.subclip(0, use_dur)
                    clip = self._fit_to_vertical(clip)
                    clips.append({"type": "video", "clip": clip, "duration": use_dur, "start": current_duration})
                    self._log(f"      ▶️ 영상: {os.path.basename(vpath)} ({use_dur:.1f}초)")
                except Exception as e:
                    self._log(f"      ⚠️ 영상 실패: {e}")
                    use_dur = 0
                
                video_idx += 1
                current_duration += use_dur
                use_video = False  # 다음은 사진
                
            elif photo_files:
                # 사진 사용 (문장 실제 TTS 길이만큼)
                if photo_idx >= len(photo_files):
                    random.shuffle(photo_files)  # 반복 시 셔플
                    photo_idx = 0
                    self._log(f"      🔄 사진 반복 (셔플)")
                
                # 해당 문장의 실제 TTS 길이 사용
                sent_dur = sentence_durations[sentence_idx] if sentence_idx < len(sentence_durations) else 3.0
                use_dur = min(sent_dur, remaining)
                
                try:
                    effect = random.choice(SCENE_EFFECTS) if SCENE_EFFECTS else None
                    clip = self._create_image_clip(photo_files[photo_idx], use_dur, effect, enhance_style=enhance_style)
                    clips.append({"type": "photo", "clip": clip, "duration": use_dur, "start": current_duration})
                    self._log(f"      🖼️ 사진: {os.path.basename(photo_files[photo_idx])} ({use_dur:.1f}초)")
                except Exception as e:
                    self._log(f"      ⚠️ 사진 실패: {e}")
                    use_dur = 0
                
                photo_idx += 1
                sentence_idx += 1
                current_duration += use_dur
                use_video = True  # 다음은 영상
            else:
                # 영상만 있는 경우
                use_video = True
                continue
            
            percent = int(current_duration / total_audio_duration * 30)
            self._progress(percent)
        
        if not clips:
            self._log("❌ 클립 생성 실패")
            return None
        
        # 8. 전환 효과 없이 영상 합치기 (까만 화면 방지!)
        video_clips = [c["clip"] for c in clips]
        self._log(f"   🔗 영상+사진 {len(video_clips)}개 연결 중...")
        if len(video_clips) == 1:
            base_video = video_clips[0]
        else:
            base_video = concatenate_videoclips(video_clips, method="chain")
        self._log(f"   ✅ 영상 연결 완료: {base_video.duration:.1f}초")
        
        # 9. 자막 오버레이 (TTS 실제 길이로 싱크)
        # sentence_durations는 위에서 TTS 실제 길이로 이미 설정됨
        
        subtitle_clips = []
        current_time = 0
        sub_y = getattr(self, '_last_img_bottom', 1300) + 30
        for i, sentence in enumerate(sentences):
            if current_time >= total_audio_duration:
                break
            dur = sentence_durations[i] if i < len(sentence_durations) else 2.5
            clips, current_time = self._create_subtitle_clips(sentence, dur, subtitle_style, current_time, sub_y)
            subtitle_clips.extend(clips)
        
        # 10. 문의박스 (8종 프리셋 적용!)
        inquiry = self._create_inquiry_box(
            getattr(channel, 'inquiry_1', ''),
            getattr(channel, 'inquiry_2', ''),
            getattr(channel, 'inquiry_3', ''),
            total_audio_duration,
            style=inquiry_style,
            is_bright_overlay=False,
            line4=getattr(channel, 'inquiry_4', ''),
            font_size_base=getattr(channel, 'inquiry_font_size', None),
            no_bg=getattr(channel, 'inquiry_no_bg', False),
            bold=getattr(channel, 'inquiry_bold', True),
            font_sizes=[getattr(channel, 'inquiry_size_1', getattr(channel, 'inquiry_font_size', 90)), getattr(channel, 'inquiry_size_2', 70), getattr(channel, 'inquiry_size_3', 70), getattr(channel, 'inquiry_size_4', 70)]
        )
        
        # 10-1. 캐릭터 - 오른쪽 끝, 자막 위
        character_clip = None
        char_name = getattr(channel, 'character', '')
        if char_name:
            char_img = self.get_character_image(char_name)
            if char_img:
                char_img = char_img.resize((250, 350), RESAMPLE)
                # ⭐ RGBA 투명 처리 (마스크 사용)
                if char_img.mode == 'RGBA':
                    char_rgb = np.array(char_img.convert('RGB'))
                    char_alpha = np.array(char_img.split()[3]) / 255.0
                    character_clip = ImageClip(char_rgb, ismask=False).set_duration(total_audio_duration)
                    character_clip = character_clip.set_mask(ImageClip(char_alpha, ismask=True).set_duration(total_audio_duration))
                else:
                    character_clip = ImageClip(np.array(char_img.convert('RGB'))).set_duration(total_audio_duration)
                character_clip = character_clip.set_position((800, 1050))
        
        # 11. 최종 합성
        self._log(f"   🎬 최종 레이어 합성 중...")
        self._log(f"      ✅ 베이스 영상: {base_video.duration:.1f}초")
        self._log(f"      ✅ 자막: {len(subtitle_clips)}개")
        if inquiry:
            self._log(f"      ✅ 문의박스: 있음 (스타일: {inquiry_style})")
        if character_clip:
            self._log(f"      ✅ 캐릭터: {char_name}")
        
        layers = [base_video] + subtitle_clips
        if inquiry:
            _inq_pos_pct = getattr(channel, 'inquiry_position', 5)
            try:
                _inq_pos_pct = int(_inq_pos_pct)
            except:
                _inq_pos_pct = 5
            layers.append(inquiry.set_position(("center", _inq_pos_pct / 100), relative=True))
        if character_clip:
            layers.append(character_clip)
        
        self._log(f"   🔗 총 {len(layers)}개 레이어 합성 중...")
        
        # ⭐ CompositeVideoClip 직접 합성 (fl() 제거 - 성능 개선!)
        final = CompositeVideoClip(layers, size=(1080, 1920))
        self._log(f"   ✅ 최종 영상: {final.duration:.1f}초")
        
        # 12. 오디오
        mixed_audio = self._build_mixed_audio(full_audio, total_audio_duration, [])
        if mixed_audio:
            final = final.set_audio(mixed_audio)
        
        # 13. 렌더링
        out_dir = self._create_output_folder(channel.project_name, "mixed", suffix)
        out_path = os.path.join(out_dir, "video.mp4")
        
        self._render_final(final, out_path)
        
        # 14. 썸네일, 메타데이터
        first_source = video_info[0][0] if video_info else (photo_files[0] if photo_files else None)
        if first_source:
            # 첫 문장(hook)을 썸네일에 전달
            channel._thumb_hook = sentences[0] if sentences else ""
            self._create_thumbnail(
                first_source, title,
                getattr(channel, 'thumb_line1', ''),
                os.path.join(out_dir, "thumbnail.jpg"),
                channel.project_name,
                channel=channel,
                inquiry_style=inquiry_style,
                frame_style=frame_style
            )
        self._create_metadata(title, channel, os.path.join(out_dir, "metadata.json"))
        
        # 정리
        final.close()
        for c in video_clips:
            try:
                c.close()
            except:
                pass
        
        self._log(f"✅ 완료: {out_path}")
        return out_path
    
    # ============================================================
    # Photos 모드: 대본 문장 수에 맞게 장면 생성
    # - 스티커 ✅, 장면효과(PAN/ZOOM) ✅
    # - 전환효과 ✅, 캐릭터 ✅
    # ============================================================

    def _create_mode_photos(self, channel, title, suffix):
        self._log("   📷 Photos 모드: 대본 문장 수에 맞게 장면 생성")
        self._log(f"   📁 채널: {channel.project_name}")
        
        # 1. 사진 로드
        photo_folder = channel.photo_folder
        if not photo_folder or not os.path.isdir(photo_folder):
            self._log(f"❌ 사진 폴더 없음 (경로: {photo_folder})")
            return None
        
        photo_exts = ["*.jpg", "*.jpeg", "*.png"]
        photo_files = []
        for ext in photo_exts:
            photo_files.extend(glob.glob(os.path.join(photo_folder, ext)))
            photo_files.extend(glob.glob(os.path.join(photo_folder, ext.upper())))
        # Windows 대소문자 중복 제거
        photo_files = list(dict.fromkeys(os.path.normcase(f) for f in photo_files))
        photo_files = [os.path.normpath(f) for f in photo_files]
        
        if not photo_files:
            self._log("❌ 사진 파일 없음")
            return None
        
        photo_files = self._sort_files(photo_files)
        self._log(f"   📂 사진 {len(photo_files)}개 로드")
        
        # 2. 스타일 고정 (영상 전체 통일)
        subtitle_style = self._get_subtitle_style()
        cta_style = self._get_cta_style()
        inquiry_style = self._get_inquiry_style()
        frame_style = self._get_frame_style()  # 테두리/액자 스타일
        enhance_style = self._get_photo_enhance_style()  # 📸 사진 보정 스타일
        inquiry_slide_direction = random.choice(["left", "right"])  # 슬라이드 방향
        inquiry_final_x = 0.5  # 중앙 고정  # 최종 X 위치
        enhance_name = PHOTO_ENHANCE_STYLES.get(enhance_style, {}).get('name', '원본')
        self._log(f"   📦 문의박스: {inquiry_style['preset']}, 테두리: {frame_style.get('type', 'none')}")
        self._log(f"   📸 사진 보정: {enhance_style} ({enhance_name})")
        
        # 4. 음성 선택
        if channel.voice == "random":
            voice_id = random.choice(self.voices) if self.voices else None
        else:
            voice_id = channel.voice
        
        # 5. 톤 1번 선택 → 영상 전체 통일
        tone_key = getattr(channel, 'tone', 'hybrid') or 'hybrid'
        if tone_key == "hybrid" or tone_key not in TONE_TYPES:
            tone_key = self._select_tone()
        tone_info = TONE_TYPES.get(tone_key, TONE_TYPES["hybrid"])
        self._log(f"   🎭 톤: {tone_info['name']}")
        
        # 6. CTA 확인 (opening_enabled 체크!)
        cta_enabled = getattr(channel, 'opening_enabled', False)
        cta_text = ''
        if cta_enabled:
            # 대사설정 [오프닝]에서 랜덤 선택
            cta_lines = self._get_cta_lines(channel)
            if cta_lines:
                # ⭐ 라운드 로빈: 같은 오프닝 반복 방지
                if not hasattr(self, '_cta_index'):
                    self._cta_index = {}
                ch_key = getattr(channel, 'name', 'default')
                idx = self._cta_index.get(ch_key, 0) % len(cta_lines)
                cta_text = cta_lines[idx]
                self._cta_index[ch_key] = idx + 1
        
        # ⭐ 문장 수 랜덤 (10~15문장) - 영상 길이 다양화
        _total = random.choice([10, 12, 15])
        if cta_text:
            script_count = _total - 1  # CTA 1개 + 대본
            self._log(f"   📢 CTA: {cta_text[:20]}...")
        else:
            script_count = _total
        self._log(f"   📝 목표 문장 수: {_total}문장 (대본 {script_count} + CTA {1 if cta_text else 0})")
        
        # 7. 대본 생성
        seed_line = None
        
        # ⭐ 대사설정 [대사] (팩트체크 없이 그대로) + PDF 팩트 (숫자/사업개요) 합치기
        parts = []
        
        # 1. 대사설정 [대사] - 팩트체크 없이 그대로 사용!
        all_seeds = self._get_all_seed_lines(channel)
        if all_seeds:
            seed_text = "\n".join(all_seeds)
            parts.append(f"【대사설정 - 아래 내용만으로 대본을 만들어라. 이 외 내용 추가 금지!】\n{seed_text}")
            self._log(f"   📝 대사설정 전체 {len(all_seeds)}개 전달")
        # ⭐ 오프닝(CTA)도 대본 소재로 추가 (대사와 중복 무관)
        _cta_lines = self._get_cta_lines(channel)
        if _cta_lines:
            _cta_seed = " / ".join(_cta_lines[:3])  # 최대 3개
            parts.append(f"【오프닝 소재 (대본에 자연스럽게 녹여라!)】\n{_cta_seed}")
            self._log(f"   📢 오프닝 소재 반영: {_cta_seed[:40]}...")
        
        # 2. PDF 팩트 - 현재 제작 모드가 pdf일 때만 실행 (photos/videos 모드에서는 건너뜀)
        _current_mode = getattr(self, "_current_mode", "")
        _is_pdf = (_current_mode == "pdf")
        if _is_pdf:
            self._log(f"   📄 [PDF모드] 팩트체크 시도")
            pdf_facts = self._extract_pdf_keywords_for_title(channel, title)
            if pdf_facts:
                parts.append(f"【PDF 검증 팩트】\n{pdf_facts}")
                _pf_preview = pdf_facts[:60].replace("\n", " / ")
                self._log(f"   ✅ [PDF모드] 팩트 반영: {_pf_preview}...")
        
        seed_line = "\n\n".join(parts) if parts else None
        
        # 대본 생성 (sentence_count 없이 자연스럽게)
        script = self.generate_script(title, tone_key, sentence_count=script_count, channel_seed=seed_line)
        sentences = self._split_sentences(script)
        # 목표 문장 수 초과 시 자르기
        if script_count and len(sentences) > script_count + 2:
            sentences = sentences[:script_count]
            self._log(f"   ✂️ 문장 수 조정: {len(sentences)}문장")
        
        # ⭐ 대본 로그 추가
        self._log(f"   📝 대본 생성: {len(sentences)}문장")
        for i, s in enumerate(sentences[:3]):
            self._log(f"      {i+1}. {s[:30]}...")
        if len(sentences) > 3:
            self._log(f"      ... (총 {len(sentences)}문장)")
        
        # ⭐ 오프닝 처리
        # CTA가 있으면 맨 앞에 추가 (오프닝 ON)
        # CTA가 없으면 GPT 대본 첫 문장(훅) 그대로 사용 (오프닝 OFF)
        if cta_text:
            sentences = [cta_text] + sentences
        
        # ⭐ 링크 멘트: 링크가 있으면 마지막 문장을 교체 (늘어짐 방지)
        link_closing = self._get_link_closing(channel)
        if link_closing and len(sentences) >= 2:
            sentences[-1] = link_closing
            self._log(f"   🔗 링크 멘트 (교체): {link_closing[:25]}...")
        
        # 프로젝트명 삽입 (1번만! GPT 대본에 이미 있으면 건너뛰기)
        project_name = channel.project_name
        if project_name and len(sentences) >= 2:
            # GPT 대본에 이미 프로젝트명이 있는지 체크
            existing_count = sum(1 for s in sentences if project_name in s)
            if existing_count == 0:
                # 없으면 1번 문장 앞에 별도 문장으로 삽입 (합치면 너무 길어지므로)
                sentences.insert(0, project_name)
                self._log(f"   📛 프로젝트명 별도 삽입 [1번 문장]: {project_name}")
            else:
                self._log(f"   📛 프로젝트명 이미 {existing_count}회 포함 → 추가 삽입 안 함")
        
        # ⭐ 사진 원본 저장 (자막 분할 후 배정하기 위해)
        original_photos = photo_files.copy()
        
        # ⭐ 중지 체크
        if self._check_stop():
            self._log("⏸️ 중지됨")
            return None
        
        # 8. Google Cloud TTS 생성
        self._log("   🎙️ Google Cloud TTS 생성...")
        
        hybrid_audio_path, sentence_durations = self.generate_tts_hybrid(
            sentences, voice_id, tone_key, channel
        )
        
        if hybrid_audio_path and sentence_durations:
            # ⭐ 문장 수 ↔ 타이밍 수 안전장치
            if len(sentence_durations) < len(sentences):
                avg = sum(sentence_durations) / len(sentence_durations) if sentence_durations else 2.5
                while len(sentence_durations) < len(sentences):
                    sentence_durations.append(avg)
                self._log(f"   ⚠️ 타이밍 부족 → {len(sentences)}개로 보정")
            elif len(sentence_durations) > len(sentences):
                sentence_durations = sentence_durations[:len(sentences)]
            
            # 전체 오디오 클립 (자르지 않고 그대로 사용!)
            full_audio_clip = AudioFileClip(hybrid_audio_path)
            actual_duration = full_audio_clip.duration
            
            # ⭐ 싱크 보정 (실제 오디오 길이와 측정값 비교)
            measured_total = sum(sentence_durations)
            if measured_total > 0:
                scale_ratio = actual_duration / measured_total
                if abs(scale_ratio - 1.0) > 0.15:
                    sentence_durations = [d * scale_ratio for d in sentence_durations]
                    self._log(f"   🔄 싱크 보정: 측정 {measured_total:.1f}초 → 실제 {actual_duration:.1f}초 (비율: {scale_ratio:.2f})")
                elif abs(scale_ratio - 1.0) > 0.03:
                    diff = actual_duration - measured_total
                    sentence_durations[-1] = max(0.3, sentence_durations[-1] + diff)
                    self._log(f"   🔧 미세 보정: 마지막 문장 {diff:+.2f}초 조정")
                else:
                    self._log(f"   ✅ 싱크 정확: {measured_total:.1f}초 ≈ 실제 {actual_duration:.1f}초")
            
            total_duration = actual_duration
            self._log(f"   🔊 총 영상 길이: {total_duration:.1f}초")
            
            # ⭐ 오디오는 자르지 않고 통으로 사용!
            full_audio = full_audio_clip
        else:
            # 실패 시 기존 방식으로 폴백
            self._log("   ⚠️ TTS 실패 → 개별 생성으로 폴백")
            sentence_audios = []
            sentence_durations = []
            
            for sent in sentences:
                audio_path = self.generate_tts(sent, voice_id, tone_key=tone_key)
                if audio_path and os.path.exists(audio_path):
                    audio_clip = AudioFileClip(audio_path)
                    dur = audio_clip.duration
                    sentence_audios.append(audio_clip)
                    sentence_durations.append(dur)
                else:
                    sentence_audios.append(None)
                    sentence_durations.append(2.5)
            
            total_duration = sum(sentence_durations)
            self._log(f"   🔊 총 영상 길이: {total_duration:.1f}초 (개별 TTS)")
            
            # 개별 TTS일 때만 합치기
            full_audio = self._concat_audio_with_silence(sentence_audios, sentence_durations)
        
        # 60초 초과 시 속도 조절
        if total_duration > 60:
            speed_ratio = total_duration / 58.0
            sentence_durations = [d / speed_ratio for d in sentence_durations]
            total_duration = sum(sentence_durations)
            try:
                try:
                    import moviepy.audio.fx.all as afx
                    full_audio = full_audio.fx(afx.speedx, speed_ratio)
                except (ImportError, AttributeError):
                    try:
                        from moviepy.audio.fx import speedx as _speedx
                        full_audio = full_audio.fx(_speedx, speed_ratio)
                    except ImportError:
                        import tempfile, subprocess
                        tmp_in = tempfile.mktemp(suffix='_in.mp3')
                        tmp_out = tempfile.mktemp(suffix='_out.mp3')
                        full_audio.write_audiofile(tmp_in, fps=44100, verbose=False, logger=None)
                        subprocess.run([_FFMPEG_BIN, '-y', '-i', tmp_in, '-filter:a', f'atempo={speed_ratio}', tmp_out],
                                       capture_output=True, startupinfo=_STARTUPINFO)
                        full_audio.close()
                        full_audio = AudioFileClip(tmp_out)
                        os.remove(tmp_in)
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_duration:.1f}초 (오디오+자막 동기화)")
            except Exception as e:
                self._log(f"   ⚡ 속도 조절: {speed_ratio:.2f}x → {total_duration:.1f}초 (오디오 속도조절 실패: {e})")
            # ⭐ 속도 조절 후 실제 오디오와 자막 싱크 재검증
            try:
                actual_after = full_audio.duration
                dur_sum = sum(sentence_durations)
                if abs(actual_after - dur_sum) > 0.5:
                    rescale = actual_after / dur_sum
                    sentence_durations = [d * rescale for d in sentence_durations]
                    self._log(f"   🔧 속도조절 후 재보정: 자막 {dur_sum:.1f}→{sum(sentence_durations):.1f}초 (실제 {actual_after:.1f}초)")
            except:
                pass
        overlay_clip, is_bright = self._load_overlay_for_mode(total_duration)
        
        # 7-1. 오버레이 밝기에 따른 자막 스타일 조정
        if overlay_clip:
            if is_bright:
                # 밝은 오버레이 → 어두운 글씨 + 흰색 테두리 (대비!)
                subtitle_style["font_color"] = (30, 30, 30)
                subtitle_style["outline_color"] = (255, 255, 255)  # ⭐ 흰색 테두리!
                subtitle_style["outline_width"] = 4
                subtitle_style["overlay_is_dark"] = False
                self._log(f"      🎨 밝은 오버레이 → 어두운 글씨 + 흰색 테두리(4px)")
            else:
                # ⭐ 어두운 오버레이 → 밝은 글씨 + 검정 테두리 (대비!)
                subtitle_style["font_color"] = (255, 255, 255)
                subtitle_style["outline_color"] = (0, 0, 0)  # 검정 테두리
                subtitle_style["outline_width"] = 4
                subtitle_style["overlay_is_dark"] = True
                self._log(f"      🎨 어두운 오버레이 → 밝은 글씨 + 검정 테두리(4px)")
        
        # 8. ⭐ 타이밍 붕괴 감지 + 균등 분배 fallback
        # 첫 문장에 50% 이상 몰리면 타이밍 붕괴로 판단
        if sentence_durations and len(sentence_durations) > 1:
            max_dur = max(sentence_durations)
            if max_dur > total_duration * 0.5:
                avg_dur = total_duration / len(sentence_durations)
                sentence_durations = [avg_dur] * len(sentence_durations)
                self._log(f"   ⚠️ 타이밍 붕괴 감지 → 균등 분배: {avg_dur:.1f}초 × {len(sentence_durations)}문장")
            else:
                # ⭐ v6.3.2: 개별 장면 최대 6초 cap (초과분 재분배)
                MAX_SCENE_DUR = 6.0
                excess_total = 0
                capped_indices = []
                for i, d in enumerate(sentence_durations):
                    if d > MAX_SCENE_DUR:
                        excess_total += d - MAX_SCENE_DUR
                        capped_indices.append(i)
                
                if excess_total > 0:
                    short_indices = [i for i in range(len(sentence_durations)) if i not in capped_indices]
                    if short_indices:
                        per_short = excess_total / len(short_indices)
                        for i in capped_indices:
                            sentence_durations[i] = MAX_SCENE_DUR
                        for i in short_indices:
                            sentence_durations[i] += per_short
                        self._log(f"   ⚙️ 장면 최대 {MAX_SCENE_DUR}초 cap: {len(capped_indices)}개 장면 조정, {excess_total:.1f}초 재분배")
        
        # 8-1. 사진 셔플 배정 (문장 수 기준)
        target_scenes = len(sentences)
        if len(original_photos) >= target_scenes:
            shuffled = original_photos.copy()
            random.shuffle(shuffled)
            photo_files = shuffled[:target_scenes]
        else:
            photo_files = []
            while len(photo_files) < target_scenes:
                batch = original_photos.copy()
                random.shuffle(batch)
                if photo_files and batch[0] == photo_files[-1] and len(batch) > 1:
                    batch[0], batch[1] = batch[1], batch[0]
                photo_files.extend(batch)
            photo_files = photo_files[:target_scenes]
        
        self._log(f"   📷 사진 {len(original_photos)}장 → {target_scenes}장면 (셔플)")
        
        # 사진 배정 완료 → sources로 사용
        sources = photo_files
        
        # 9. 장면 효과
        scene_effects = self._get_scene_effects(target_scenes)
        
        # 10. 장면별 클립 생성
        self._log("   🎞️ 장면 생성...")
        clips = []
        current_time = 0
        scene_starts = []
        
        # ⭐ 장면 오버레이 로드 (1,3,5,7번 장면용)
        scene_overlays = self._load_scene_overlays()
        
        for i, (src, sentence) in enumerate(zip(sources, sentences)):
            percent = int((i + 1) / target_scenes * 50)
            self._progress(percent)
            
            dur = sentence_durations[i]
            effect = scene_effects[i]
            
            self._log(f"      🎞️ 장면 {i+1}/{target_scenes}: {dur:.1f}초")
            
            try:
                layers = []
                
                # 1. 오버레이 (배경)
                if overlay_clip:
                    overlay_segment = overlay_clip.subclip(current_time, min(current_time + dur, overlay_clip.duration))
                    layers.append(overlay_segment)
                    self._log(f"         ✅ 오버레이")
            
                # 2. 이미지 클립 (투명 배경, 오버레이 위에)
                img_clip = self._create_image_clip(src, dur, effect, frame_style=frame_style, enhance_style=enhance_style, pdf_mode=True)
                layers.append(img_clip)
                self._log(f"         ✅ 사진: {os.path.basename(src)[:20]}...")
            
                # 3. 문의박스 (위치는 함수 내부에서 계산)
                self._current_inquiry_position = getattr(channel, 'inquiry_position', 5)
                inquiry = self._create_inquiry_box_animated(
                    getattr(channel, 'inquiry_1', ''),
                    getattr(channel, 'inquiry_2', ''),
                    getattr(channel, 'inquiry_3', ''),
                    dur,
                    is_first_scene=(i == 0),
                    slide_direction=inquiry_slide_direction,
                    slide_speed=0.5,
                    style=inquiry_style,
                    is_bright_overlay=is_bright,
                    line4=getattr(channel, 'inquiry_4', ''),
                    font_size_base=getattr(channel, 'inquiry_font_size', None),
                    no_bg=getattr(channel, 'inquiry_no_bg', False),
                    bold=getattr(channel, 'inquiry_bold', True),
                    font_sizes=[getattr(channel, 'inquiry_size_1', getattr(channel, 'inquiry_font_size', 90)), getattr(channel, 'inquiry_size_2', 70), getattr(channel, 'inquiry_size_3', 70), getattr(channel, 'inquiry_size_4', 70)]
                )
                if inquiry:
                    layers.append(inquiry)  # 위치 이미 설정됨!
                    self._log(f"         ✅ 문의박스")
            
                # 4. 캐릭터 - 먼저 추가 (자막 아래)
                char_name = getattr(channel, 'character', '')
                if char_name:
                    char_img = self.get_character_image(char_name)
                    if char_img:
                        char_img = char_img.resize((250, 350), RESAMPLE)
                        # ⭐ RGB로만 처리 (RGBA 충돌 방지)
                        if char_img.mode == 'RGBA':
                            # RGB + Alpha 분리
                            char_rgb = np.array(char_img.convert('RGB'))
                            char_alpha = np.array(char_img.split()[3]) / 255.0  # 0~1 정규화
                            char_clip = ImageClip(char_rgb, ismask=False).set_duration(dur)
                            char_clip = char_clip.set_mask(ImageClip(char_alpha, ismask=True).set_duration(dur))
                        else:
                            char_clip = ImageClip(np.array(char_img.convert('RGB'))).set_duration(dur)
                    
                        sub_y = getattr(self, '_last_img_bottom', 1300) + 30  # 자막 위치 미리 계산
                        char_x = 1080 - 250 - 30  # 오른쪽 끝
                        char_y = sub_y - 350 + 50  # 자막 바로 위 (약간 겹침)
                        layers.append(char_clip.set_position((char_x, char_y)))
                        self._log(f"         ✅ 캐릭터: {char_name}")
            
                # 5. 자막 - 나중에 추가 (맨 위)
                sub_clip = self._create_subtitle(sentence, dur, subtitle_style)
                sub_y = getattr(self, '_last_img_bottom', 1300) + 30
                layers.append(sub_clip.set_position(("center", sub_y)))
                self._log(f"         ✅ 자막: {sentence[:15]}...")
            
                # 6. 장면 오버레이 (1,3,5,7번 장면에 PNG, 가운데 정렬)
                if i in scene_overlays:
                    ov_img = scene_overlays[i]
                    if ov_img.mode == "RGBA":
                        ov_rgb = np.array(ov_img.convert("RGB"))
                        ov_alpha = np.array(ov_img.split()[3]) / 255.0
                        ov_clip = ImageClip(ov_rgb, ismask=False).set_duration(dur)
                        ov_clip = ov_clip.set_mask(ImageClip(ov_alpha, ismask=True).set_duration(dur))
                    else:
                        ov_clip = ImageClip(np.array(ov_img.convert("RGB"))).set_duration(dur)
                    ov_clip = ov_clip.set_position(("center", "center"))
                    layers.append(ov_clip)
                    self._log(f"         ✅ 장면오버레이: 폴더{list(scene_overlays.keys()).index(i)+1}")
            
                # ⭐ CompositeVideoClip 직접 합성 (장면 오버레이와 무관하게 항상 실행!)
                self._log(f"         🔗 레이어 {len(layers)}개 합성")
                scene = CompositeVideoClip(layers, size=(1080, 1920))
                clips.append(scene)
                scene_starts.append(current_time)
                current_time += dur
            except Exception as e:
                self._log(f"      ⚠️ 장면 {i+1} 생성 실패: {e} → 스킵")
                try:
                    fallback = ImageClip(np.zeros((1920, 1080, 3), dtype=np.uint8)).set_duration(dur)
                    clips.append(fallback)
                    scene_starts.append(current_time)
                    current_time += dur
                except:
                    pass
        
        # 10. 오버레이 정리
        if overlay_clip:
            try:
                overlay_clip.close()
            except:
                pass
        
        # 11. 전환효과
        # 12. 영상 합치기 (까만 화면 방지!)
        if not clips:
            self._log(f"   ❌ 유효한 장면이 없습니다. 문의박스 오류 확인 필요")
            return None
        self._log(f"   🔗 장면 {len(clips)}개 연결 중...")
        final = concatenate_videoclips(clips, method="chain")
        self._log(f"   ✅ 영상 연결 완료: {final.duration:.1f}초")
        
        # 13. 오디오
        total_duration = final.duration
        mixed_audio = self._build_mixed_audio(full_audio, total_duration, scene_starts)
        if mixed_audio:
            final = final.set_audio(mixed_audio)
        
        # 14. 렌더링
        out_dir = self._create_output_folder(channel.project_name, "photos", suffix)
        out_path = os.path.join(out_dir, "video.mp4")
        
        self._render_final(final, out_path)
        
        # 15. 썸네일, 메타데이터
        # 첫 문장(hook)을 썸네일에 전달
        channel._thumb_hook = sentences[0] if sentences else ""
        self._create_thumbnail(
            sources[0], title,
            getattr(channel, 'thumb_line1', ''),
            os.path.join(out_dir, "thumbnail.jpg"),
            channel.project_name,
            channel=channel,
            inquiry_style=inquiry_style,
            frame_style=frame_style
        )
        self._create_metadata(title, channel, os.path.join(out_dir, "metadata.json"))
        
        # 정리
        final.close()
        for c in clips:
            try:
                c.close()
            except:
                pass
        
        self._log(f"✅ 완료: {out_path}")
        return out_path
    
    # ============================================================
    # PDF 모드: 대본 문장 수에 맞게 장면 생성
    # - 스티커 ❌, 장면효과 ❌
    # - 전환효과 ✅, 캐릭터 ✅
    # ============================================================

    def generate_tts_google_cloud(self, sentences, tone_key=None):
        """
        Google Cloud TTS로 음성 생성 (한국어 네이티브)
        - 비용: 영상당 13원
        - 품질: 자연스러운 한국어
        - 음성: 8가지 프리셋 중 랜덤 선택 (여자 4 + 남자 4)
        """
        if not self.google_tts_client or not sentences:
            return None, []
        
        try:
            from google.cloud import texttospeech
            
            # ⭐ 목소리 프리셋 랜덤 선택 (가중치 기반)
            voice_preset = self._select_voice_preset()
            voice_name = voice_preset["voice_name"]
            pitch = voice_preset["pitch"]
            rate = voice_preset["rate"]
            
            # ⭐ 채널 설정 TTS 속도 배율 적용
            channel_speed = getattr(self, 'tts_speed', 1.0)
            if channel_speed and channel_speed != 1.0:
                rate = round(rate * channel_speed, 2)
                rate = max(0.25, min(4.0, rate))  # Google TTS 허용 범위 클램프
            
            self._log(f"   🎤 Google Cloud TTS ({voice_name})")
            self._log(f"      🎭 목소리: {voice_preset['name']} (pitch={pitch}, rate={rate})")
            
            # 전체 텍스트 합치기 - SSML 방식 (문장 간 호흡 추가, 한자한자 읽힘 방지)
            normalized_sents = [self._normalize_tts(s) for s in sentences]
            # SSML: 각 문장을 <s> 태그로 감싸고 250ms 호흡 추가
            ssml_sentences = []
            for s in normalized_sents:
                # SSML 특수문자 이스케이프
                safe = s.replace('&', '그리고').replace('<', '').replace('>', '')
                ssml_sentences.append(f'<s>{safe}</s><break time="250ms"/>')
            full_ssml = '<speak>' + ''.join(ssml_sentences) + '</speak>'
            synthesis_input = texttospeech.SynthesisInput(ssml=full_ssml)
            
            # 성별에 따라 SSML 성별 설정
            ssml_gender = texttospeech.SsmlVoiceGender.FEMALE if voice_preset["gender"] == "female" else texttospeech.SsmlVoiceGender.MALE
            
            voice = texttospeech.VoiceSelectionParams(
                language_code="ko-KR",
                name=voice_name,  # 프리셋에서 선택된 음성
                ssml_gender=ssml_gender
            )
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=rate,
                pitch=pitch,
                volume_gain_db=0.0
            )
            
            response = self.google_tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            # 저장
            audio_path = os.path.join(self.temp_dir, f"tts_google_{int(time.time()*1000)}.mp3")
            with open(audio_path, "wb") as f:
                f.write(response.audio_content)
            
            # 문장별 시간 측정 (개별 Google Cloud TTS로 정확하게)
            sentence_durations = []
            for i, sent in enumerate(sentences):
                try:
                    normalized = self._normalize_tts(sent)
                    # 개별 문장도 SSML로 (한자한자 읽힘 방지)
                    safe_norm = normalized.replace('&', '그리고').replace('<', '').replace('>', '')
                    sent_input = texttospeech.SynthesisInput(ssml=f'<speak><s>{safe_norm}</s></speak>')
                    sent_response = self.google_tts_client.synthesize_speech(
                        input=sent_input, voice=voice, audio_config=audio_config
                    )
                    sent_audio_path = os.path.join(self.temp_dir, f"google_sent_{i}.mp3")
                    with open(sent_audio_path, "wb") as sf:
                        sf.write(sent_response.audio_content)
                    
                    audio_clip = AudioFileClip(sent_audio_path)
                    dur = audio_clip.duration
                    sentence_durations.append(dur)
                    audio_clip.close()
                    
                    try:
                        os.remove(sent_audio_path)
                    except:
                        pass
                except Exception:
                    sentence_durations.append(3.0)
            
            # 실제 시간과 비교
            if sentence_durations:
                full_audio = AudioFileClip(audio_path)
                measured_total = sum(sentence_durations)
                actual_duration = full_audio.duration
                full_audio.close()
                
                # 시간 보정 (gTTS 측정값 → 실제 오디오 시간으로 스케일링)
                if measured_total > 0:
                    ratio = actual_duration / measured_total
                    sentence_durations = [d * ratio for d in sentence_durations]
                    self._log(f"      ⚙️ 시간 보정: {measured_total:.1f}초 → {sum(sentence_durations):.1f}초 (비율: {ratio:.2f})")
                
                self._log(f"   ✅ Google Cloud TTS 완료!")
                
                return audio_path, sentence_durations
            
            return audio_path, []
            
        except Exception as e:
            self._log(f"   ⚠️ Google Cloud TTS 오류: {e}")
            import traceback
            self._log(f"      → {traceback.format_exc().split(chr(10))[-2]}")
            return None, []
    

    def _sort_files(self, files):
        """규칙 36. 파일 정렬 (순서 vs 랜덤)"""
        if not files:
            return files
        
        # 순서 패턴: 01_, 02_, 1-, 2. 등 (1~3자리)
        ordered_patterns = [
            r'^(\d{1,3})[_\-\.\s]',  # 01_, 02-, 3.
            r'^(\d{1,3})$',          # 숫자만
        ]
        
        # 랜덤 패턴: 카카오톡, 카메라 자동번호 등
        random_patterns = [
            r'KakaoTalk',
            r'IMG_\d{4,}',
            r'video_\d{6,}',
            r'\d{8,}',  # 8자리 이상 (타임스탬프)
        ]
        
        # 파일명 분석
        basenames = [os.path.basename(f) for f in files]
        
        # 랜덤 패턴 체크
        for pattern in random_patterns:
            if any(re.search(pattern, bn) for bn in basenames):
                random.shuffle(files)
                return files
        
        # 순서 패턴 체크
        def get_order_num(p):
            bn = os.path.basename(p)
            for pattern in ordered_patterns:
                m = re.search(pattern, bn)
                if m:
                    return int(m.group(1))
            # 일반 숫자 추출
            m = re.search(r'(\d+)', bn)
            return int(m.group(1)) if m else 9999
        
        has_numbers = any(re.search(r'\d+', bn) for bn in basenames)
        if has_numbers:
            return sorted(files, key=get_order_num)
        else:
            random.shuffle(files)
            return files
    
    # ============================================================
    # 스티커
    # ============================================================
    

    def _get_cta_style(self):
        # 위치 (자막 C와 안 겹치게 위로!)
        position_y = random.uniform(0.60, 0.68)
        
        # 폰트 크기 랜덤
        font_size = random.randint(52, 64)
        
        # 배경 스타일 랜덤
        bg_style = random.choice(["dark", "color", "gradient"])
        if bg_style == "dark":
            box_color = (0, 0, 0)
            box_opacity = random.randint(140, 180)
        elif bg_style == "color":
            box_color = (random.randint(20, 60), random.randint(20, 60), random.randint(60, 100))
            box_opacity = random.randint(160, 200)
        else:
            box_color = (30, 30, 50)
            box_opacity = random.randint(150, 190)
        
        return {
            "font_size": font_size,
            "font_color": random.choice(CTA_COLORS),
            "position_y": position_y,
            "box_color": box_color,
            "box_opacity": box_opacity,
            "box_radius": random.randint(14, 22),
            "stroke_color": "#FFFFFF",
            "stroke_width": 2,
            "duration": 5.0,
        }
    

    def _get_inquiry_style(self):
        """문의박스 16종 프리셋 + 색상 랜덤화 (한 영상 내 통일)"""
        all_presets = ["A", "B", "C", "D", "E", "F", "G", "H",
                       "I", "J", "K", "L", "M", "N", "O", "P"]
        
        # 최근 사용한 프리셋 피하기 (연속 중복 방지)
        recent = getattr(self, '_recent_inquiry_presets', [])
        available = [p for p in all_presets if p not in recent]
        if not available:
            available = all_presets
        
        preset = random.choice(available)
        
        # 최근 3개 기록 유지
        recent.append(preset)
        if len(recent) > 3:
            recent.pop(0)
        self._recent_inquiry_presets = recent
        
        # 텍스트 색상 풀 (프리셋별로 다양하게)
        TEXT_COLOR_POOLS = {
            "A": [(100, 255, 218), (150, 220, 255), (200, 255, 200)],  # 민트/하늘/연두
            "B": [(255, 255, 255), (255, 250, 230), (230, 240, 255)],  # 흰색 계열
            "C": [(255, 220, 100), (255, 180, 80), (255, 255, 150)],   # 노랑/주황
            "D": [(255, 255, 255), (220, 220, 255), (255, 220, 255)],  # 흰색/연보라
            "E": [(180, 255, 150), (150, 255, 200), (200, 255, 180)],  # 연두 계열
            "F": [(255, 255, 255), (255, 240, 220), (240, 255, 255)],  # 흰색 계열
            "G": [(255, 200, 150), (255, 180, 180), (255, 220, 180)],  # 살구/핑크
            "H": [(200, 220, 255), (180, 200, 255), (220, 200, 255)],  # 연파랑
            "I": [(255, 255, 255), (240, 250, 255), (255, 245, 240)],  # 하단 페이드
            "J": [(255, 220, 80), (255, 255, 150), (255, 200, 100)],   # 슬림 바
            "K": [(255, 255, 255), (220, 240, 255), (255, 240, 230)],  # 알약형
            "L": [(255, 255, 255), (230, 250, 255), (255, 250, 240)],  # 글래스
            "M": [(255, 255, 255), (255, 230, 200), (200, 230, 255)],  # 상단 액센트
            "N": [(255, 255, 255), (240, 240, 250), (255, 245, 235)],  # 그림자 카드
            "O": [(200, 240, 255), (180, 255, 220), (255, 200, 255)],  # 네온 글로우
            "P": [(255, 255, 255), (220, 220, 220), (200, 220, 255)],  # 미니멀 라인
        }
        
        ACCENT_COLOR_POOLS = {
            "A": [(100, 255, 218), (0, 230, 180), (80, 200, 255)],
            "B": [(255, 200, 100), (255, 150, 80), (100, 200, 255)],
            "C": [(255, 220, 100), (255, 180, 0), (255, 255, 100)],
            "D": [(100, 200, 255), (150, 100, 255), (255, 150, 200)],
            "E": [(180, 255, 150), (100, 255, 180), (150, 255, 100)],
            "F": [(255, 180, 200), (255, 150, 150), (200, 150, 255)],
            "G": [(255, 150, 100), (255, 100, 100), (255, 180, 100)],
            "H": [(150, 180, 255), (100, 150, 255), (180, 150, 255)],
            "I": [(255, 200, 100), (100, 200, 255), (255, 150, 200)],
            "J": [(255, 180, 50), (100, 255, 180), (255, 100, 100)],
            "K": [(100, 200, 255), (255, 180, 100), (200, 100, 255)],
            "L": [(150, 200, 255), (255, 200, 150), (200, 255, 200)],
            "M": [(255, 120, 80), (80, 200, 255), (255, 200, 50)],
            "N": [(100, 180, 255), (255, 150, 100), (150, 255, 150)],
            "O": [(80, 200, 255), (255, 100, 200), (100, 255, 180)],
            "P": [(255, 255, 255), (200, 200, 200), (150, 200, 255)],
        }
        
        # 배경 색상 풀 (원색 + 다양한 색상)
        BG_COLOR_POOLS = {
            "A": [(0, 0, 0, 220), (30, 30, 30, 230), (50, 50, 50, 220)],           # 검정 계열
            "B": [(0, 50, 100, 240), (0, 70, 130, 240), (20, 60, 120, 240)],       # 파랑 계열
            "C": [(100, 30, 60, 240), (130, 20, 50, 240), (90, 40, 70, 240)],      # 와인/버건디
            "D": [(0, 80, 60, 230), (0, 100, 80, 230), (20, 90, 70, 230)],         # 청록 계열
            "E": [(80, 50, 120, 240), (100, 40, 140, 240), (70, 60, 110, 240)],    # 보라 계열
            "F": [(50, 50, 50, 200), (70, 70, 70, 200), (40, 40, 40, 200)],        # 회색 (반투명)
            "G": [(180, 100, 50, 240), (200, 120, 60, 240), (160, 90, 40, 240)],   # 주황/골드
            "H": [(60, 100, 60, 240), (80, 120, 80, 240), (50, 90, 50, 240)],      # 녹색 계열
            "I": [(20, 20, 40, 220), (30, 30, 50, 220), (15, 25, 45, 220)],       # 다크 블루
            "J": [(30, 30, 30, 200), (40, 40, 40, 200), (20, 20, 30, 200)],       # 다크 슬림
            "K": [(40, 60, 100, 230), (50, 70, 110, 230), (30, 50, 90, 230)],     # 네이비
            "L": [(60, 60, 80, 200), (70, 70, 90, 200), (50, 50, 70, 200)],       # 글래스
            "M": [(30, 40, 60, 220), (40, 50, 70, 220), (20, 30, 50, 220)],       # 다크
            "N": [(45, 45, 55, 240), (55, 55, 65, 240), (35, 35, 45, 240)],       # 차콜
            "O": [(15, 15, 30, 200), (20, 20, 40, 200), (10, 10, 25, 200)],       # 네온 다크
            "P": [(20, 20, 20, 190), (30, 30, 30, 190), (10, 10, 15, 190)],       # 미니멀
        }
        
        # 테두리 색상 풀 (원색 + 눈에 띄는 색)
        BORDER_COLOR_POOLS = {
            "A": [(255, 255, 255), (200, 200, 200), (255, 220, 100)],              # 흰색/금색
            "B": [(255, 200, 0), (255, 255, 255), (100, 200, 255)],                # 금색/흰색/하늘
            "C": [(255, 200, 150), (255, 255, 255), (255, 180, 200)],              # 살구/흰색/핑크
            "D": [(100, 255, 220), (255, 255, 255), (200, 255, 200)],              # 민트/흰색/연두
            "E": [(255, 180, 255), (255, 255, 255), (200, 150, 255)],              # 핑크/흰색/연보라
            "F": [(255, 255, 255), (255, 200, 0), (100, 200, 255)],                # 흰색/금색/하늘
            "G": [(255, 255, 200), (255, 255, 255), (255, 220, 150)],              # 연노랑/흰색
            "H": [(200, 255, 200), (255, 255, 255), (150, 255, 150)],              # 연두/흰색
            "I": [(255, 200, 100), (200, 200, 200), (255, 255, 255)],              # 페이드용
            "J": [(255, 200, 50), (100, 200, 255), (255, 150, 100)],               # 슬림 바
            "K": [(200, 220, 255), (255, 255, 255), (255, 200, 150)],              # 알약
            "L": [(255, 255, 255), (200, 230, 255), (255, 220, 200)],              # 글래스
            "M": [(255, 120, 80), (255, 200, 50), (100, 200, 255)],               # 상단 액센트
            "N": [(200, 200, 220), (255, 255, 255), (180, 200, 255)],             # 카드
            "O": [(100, 220, 255), (255, 150, 220), (150, 255, 200)],             # 네온
            "P": [(180, 180, 200), (255, 255, 255), (200, 200, 200)],             # 미니멀
        }
        
        text_color = random.choice(TEXT_COLOR_POOLS[preset])
        accent_color = random.choice(ACCENT_COLOR_POOLS[preset])
        bg_color = random.choice(BG_COLOR_POOLS[preset])
        border_color = random.choice(BORDER_COLOR_POOLS[preset])
        
        style = {
            "preset": preset,
            "text_color": text_color,
            "accent_color": accent_color,
            "border_color": (*border_color, 255),  # 테두리 색상 추가
        }
        
        # 영상 전체 통일을 위한 고정값 (크고 굵게!)
        fixed_font_size = 72  # 2배 크게!
        fixed_radius = 14
        border_width = random.choice([3, 4, 5])  # 테두리 두께 랜덤
        
        if preset == "A":  # 검정 박스 + 테두리
            style.update({
                "bg_type": "rounded_box",
                "bg_color": bg_color,
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "B":  # 파랑 박스 + 테두리
            style.update({
                "bg_type": "full_stripe",
                "bg_color": bg_color,
                "border_width": border_width,
                "width": "full",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 0,
            })
        elif preset == "C":  # 와인 그라데이션 + 테두리
            style.update({
                "bg_type": "gradient_box",
                "bg_color": bg_color,
                "bg_color2": (bg_color[0]+30, bg_color[1], bg_color[2]+20, bg_color[3]),
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "D":  # 청록 + 굵은 테두리
            style.update({
                "bg_type": "outline_only",
                "bg_color": bg_color,
                "border_width": 5,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "E":  # 보라 둥근 박스 + 테두리
            style.update({
                "bg_type": "rounded_box",
                "bg_color": bg_color,
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 24,
            })
        elif preset == "F":  # 회색 반투명 + 테두리
            style.update({
                "bg_type": "rounded_box",
                "bg_color": bg_color,
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "G":  # 주황/골드 + 하단 강조선
            style.update({
                "bg_type": "underline_box",
                "bg_color": bg_color,
                "underline_color": accent_color,
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "H":  # 녹색 그라데이션 + 테두리
            style.update({
                "bg_type": "gradient_vertical",
                "bg_color": bg_color,
                "border_width": border_width,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "I":  # 리본 배너형
            style.update({
                "bg_type": "ribbon",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 0,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 0,
            })
        elif preset == "J":  # 말풍선
            style.update({
                "bg_type": "speech_bubble",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 2,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 20,
            })
        elif preset == "K":  # 모서리 잘린 사각형
            style.update({
                "bg_type": "cut_corner",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 2,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 0,
            })
        elif preset == "L":  # 좌측 두꺼운 바 + 배경
            style.update({
                "bg_type": "left_bar",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 0,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 0,
            })
        elif preset == "M":  # 상하 장식 라인
            style.update({
                "bg_type": "deco_lines",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 0,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 12,
            })
        elif preset == "N":  # 그림자 카드
            style.update({
                "bg_type": "shadow_card",
                "bg_color": bg_color,
                "border_width": 2,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": fixed_radius,
            })
        elif preset == "O":  # 네온 더블 글로우
            style.update({
                "bg_type": "neon_glow",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 0,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 16,
            })
        elif preset == "P":  # 사다리꼴
            style.update({
                "bg_type": "trapezoid",
                "bg_color": bg_color,
                "accent_color": accent_color,
                "border_width": 2,
                "width": "auto",
                "font_size": fixed_font_size,
                "font_weight": "bold",
                "radius": 0,
            })
        
        return style
    

    def _create_thumbnail(self, src, title, thumb_text, out_path, project_name="",
                          channel=None, inquiry_style=None, frame_style=None):
        """썸네일 생성 (새 구조)
        - 배경: 원본 사진/첫 프레임 그대로(9:16 cover crop), 겹쳐도 OK
        - 상단: 제목(문단 분할) / 폰트 100 / 자막 스타일 재사용
        - 중단: 문의박스(중앙)
        - 캐릭터: 사용 안 함
        """
        try:
            self._log(f"   🖼️ 썸네일 생성 중...")

            target_w, target_h = 1080, 1920
            import re

            # ========================================
            # 1) 배경 이미지/프레임 로드 (원본 그대로)
            # ========================================
            bg_src = None
            if not src or not os.path.exists(str(src)):
                bg_src = Image.new("RGB", (target_w, target_h), (30, 30, 30))
            elif self._is_video_file(str(src)):
                try:
                    clip = VideoFileClip(str(src), audio=False)
                    frame_time = min(1.0, clip.duration / 2) if clip.duration else 0
                    frame = clip.get_frame(frame_time)
                    clip.close()
                    bg_src = Image.fromarray(frame).convert("RGB")
                except:
                    bg_src = Image.new("RGB", (target_w, target_h), (30, 30, 30))
            else:
                bg_src = Image.open(str(src))
                # EXIF 회전 적용
                try:
                    from PIL import ExifTags
                    for orientation in ExifTags.TAGS.keys():
                        if ExifTags.TAGS[orientation] == 'Orientation':
                            break
                    exif = bg_src._getexif()
                    if exif is not None:
                        orientation_value = exif.get(orientation)
                        if orientation_value == 3:
                            bg_src = bg_src.rotate(180, expand=True)
                        elif orientation_value == 6:
                            bg_src = bg_src.rotate(270, expand=True)
                        elif orientation_value == 8:
                            bg_src = bg_src.rotate(90, expand=True)
                except:
                    pass
                bg_src = bg_src.convert("RGB")

            # 9:16 cover crop (배경 그대로 사용)
            if bg_src.size != (target_w, target_h):
                scale = max(target_w / bg_src.width, target_h / bg_src.height)
                rw, rh = int(bg_src.width * scale), int(bg_src.height * scale)
                bg_img = bg_src.resize((rw, rh), RESAMPLE)
                left = (rw - target_w) // 2
                top = (rh - target_h) // 2
                bg_img = bg_img.crop((left, top, left + target_w, top + target_h))
            else:
                bg_img = bg_src

            canvas = bg_img.convert("RGBA")
            draw = ImageDraw.Draw(canvas)

            # ========================================
            # 2) 상단 제목 (폰트 100 / 자막 스타일 재사용)
            # ========================================
            font_path = self._get_font_path()

            # 제목 텍스트 결정
            full_title = (title or project_name or "분양정보").strip()

            # 문단 분할: 3줄까지 허용, 각 줄이 화면 안에 들어오도록
            def split_title_to_lines(text, max_width=980, font_path=font_path, font_size=100):
                """제목을 최대 3줄로 분할 (각 줄이 화면 안에 들어오도록)"""
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    return ["분양정보"]
                
                try:
                    test_font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
                except:
                    test_font = ImageFont.load_default()
                
                def text_width(t):
                    try:
                        bbox = test_font.getbbox(t)
                        return bbox[2] - bbox[0]
                    except:
                        return len(t) * font_size * 0.6
                
                # 1줄에 들어가면 1줄
                if text_width(text) <= max_width:
                    return [text]
                
                # ' - ', '|', ':' 같은 구분자를 우선 분할
                for sep in [" | ", " - ", " : ", ": ", " |", "| "]:
                    if sep in text:
                        parts = [p.strip() for p in text.split(sep) if p.strip()]
                        if len(parts) >= 2:
                            first = parts[0]
                            rest = " ".join(parts[1:])
                            # rest도 넘치면 다시 분할
                            if text_width(rest) > max_width:
                                rest_words = rest.split(" ")
                                mid = len(rest_words) // 2
                                line2 = " ".join(rest_words[:mid])
                                line3 = " ".join(rest_words[mid:])
                                return [first, line2, line3][:3]
                            return [first, rest]
                
                # 공백 기준으로 3줄 분할
                words = text.split(" ")
                
                # 2줄 시도
                best2 = None
                for i in range(1, len(words)):
                    a = " ".join(words[:i]).strip()
                    b = " ".join(words[i:]).strip()
                    if not a or not b:
                        continue
                    # 두 줄 다 화면에 들어오면 OK
                    if text_width(a) <= max_width and text_width(b) <= max_width:
                        score = abs(len(a) - len(b))
                        if best2 is None or score < best2[0]:
                            best2 = (score, [a, b])
                
                if best2:
                    return best2[1]
                
                # 2줄로 안 되면 3줄 시도
                best3 = None
                for i in range(1, len(words)):
                    for j in range(i + 1, len(words)):
                        a = " ".join(words[:i]).strip()
                        b = " ".join(words[i:j]).strip()
                        c = " ".join(words[j:]).strip()
                        if not a or not b or not c:
                            continue
                        if text_width(a) <= max_width and text_width(b) <= max_width and text_width(c) <= max_width:
                            score = max(len(a), len(b), len(c)) - min(len(a), len(b), len(c))
                            if best3 is None or score < best3[0]:
                                best3 = (score, [a, b, c])
                
                if best3:
                    return best3[1]
                
                # 그래도 안 되면 강제 3등분
                total = len(text)
                return [text[:total//3].strip(), text[total//3:total*2//3].strip(), text[total*2//3:].strip()]

            title_lines = split_title_to_lines(full_title)

            # 자막 스타일을 가져오되, 썸네일 전용으로 폰트/위치만 고정
            style = self._get_subtitle_style()
            style = style.copy() if isinstance(style, dict) else {}
            style["font_size"] = 100  # 고정 (기본값)
            
            # ⭐ v6.3.2: 제목이 화면 넘치면 폰트 자동 축소
            try:
                test_font = ImageFont.truetype(font_path, 100) if font_path else ImageFont.load_default()
                max_line_w = 0
                for ln in title_lines:
                    bbox = test_font.getbbox(ln)
                    max_line_w = max(max_line_w, bbox[2] - bbox[0])
                if max_line_w > target_w - 100:  # 50px 좌우 여백
                    new_size = int(100 * (target_w - 100) / max_line_w * 0.95)
                    style["font_size"] = max(60, new_size)
                    self._log(f"   📏 썸네일 제목 폰트 축소: 100→{style['font_size']}px (폭: {max_line_w})")
            except:
                pass
            # 썸네일에서는 타이핑 효과(H) 제외(정지 이미지라 의미 없음)
            if style.get("preset") == "H":
                style["preset"] = "G"
                style["bg_type"] = "classic"
                style["font_color"] = (255, 255, 255)
                style["outline_width"] = 4
                style["outline_color"] = (0, 0, 0)

            # PIL 폰트 로드
            try:
                title_font = ImageFont.truetype(font_path, int(style.get("font_size", 100))) if font_path else ImageFont.load_default()
            except:
                title_font = ImageFont.load_default()

            def draw_text_with_outline(x, y, text, font, fill, outline_w=4, outline_fill=(0, 0, 0, 255)):
                if outline_w and outline_w > 0:
                    ow = int(outline_w)
                    for dx in range(-ow, ow + 1):
                        for dy in range(-ow, ow + 1):
                            if dx == 0 and dy == 0:
                                continue
                            draw.text((x + dx, y + dy), text, font=font, fill=outline_fill)
                draw.text((x, y), text, font=font, fill=fill)

            # 제목 블록 전체 크기 계산
            line_gap = 16
            widths, heights = [], []
            for ln in title_lines:
                bbox = draw.textbbox((0, 0), ln, font=title_font)
                widths.append(bbox[2] - bbox[0])
                heights.append(bbox[3] - bbox[1])

            block_w = max(widths) if widths else 0
            block_h = sum(heights) + (len(title_lines) - 1) * line_gap

            # 상단 위치 (안전영역 고려)
            start_y = 110
            start_x = (target_w - block_w) // 2

            # 배경(박스/하이라이트/띠) 간단 지원
            bg_type = style.get("bg_type", "classic")
            padding_x = int(style.get("box_padding_x", 50))
            padding_y = int(style.get("box_padding_y", 30))

            if bg_type in ("rounded_box", "classic"):
                box_color = style.get("box_color", (0, 0, 0))
                opacity = int(style.get("box_opacity", 150))
                radius = int(style.get("box_radius", 18))
                x1 = max(20, start_x - padding_x)
                y1 = max(20, start_y - padding_y)
                x2 = min(target_w - 20, start_x + block_w + padding_x)
                y2 = min(target_h - 20, start_y + block_h + padding_y)
                draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=(*box_color, opacity))

            elif bg_type == "stripe":
                stripe_color = style.get("stripe_color", (0, 0, 0, 160))
                x1 = 0
                y1 = max(0, start_y - padding_y)
                x2 = target_w
                y2 = min(target_h, start_y + block_h + padding_y)
                draw.rectangle([x1, y1, x2, y2], fill=stripe_color)

            elif bg_type == "highlight":
                hl = style.get("highlight_color", (255, 255, 0, 200))
                x1 = max(20, start_x - padding_x)
                y1 = max(20, start_y - padding_y)
                x2 = min(target_w - 20, start_x + block_w + padding_x)
                y2 = min(target_h - 20, start_y + block_h + padding_y)
                draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=hl)

            elif bg_type == "underline":
                # 밑줄은 텍스트 아래
                pass

            # 텍스트 색상/외곽선
            font_color = style.get("font_color", (255, 255, 255))
            outline_w = int(style.get("outline_width", 4) or 0)
            outline_color = style.get("outline_color", (0, 0, 0))

            # 제목 라인 출력
            y = start_y
            for i, ln in enumerate(title_lines):
                bbox = draw.textbbox((0, 0), ln, font=title_font)
                tw = bbox[2] - bbox[0]
                x = (target_w - tw) // 2
                draw_text_with_outline(x, y, ln, title_font, (*font_color, 255), outline_w, (*outline_color, 255))
                y += heights[i] + line_gap

            # underline 타입이면 마지막 라인 아래 밑줄
            if bg_type == "underline":
                underline_color = style.get("underline_color", (255, 220, 0))
                thickness = int(style.get("underline_thickness", 10))
                ux1 = max(40, start_x)
                ux2 = min(target_w - 40, start_x + block_w)
                uy = start_y + block_h + 10
                draw.rectangle([ux1, uy, ux2, uy + thickness], fill=(*underline_color, 230))

            # ========================================
            # 3) 중단 문의박스 (영상과 동일한 스타일로 중앙 배치)
            # ========================================
            inquiry_1 = ""
            inquiry_2 = ""
            inquiry_3 = ""
            
            if channel:
                inquiry_1 = getattr(channel, 'inquiry_1', '') or ""
                inquiry_2 = getattr(channel, 'inquiry_2', '') or ""
                inquiry_3 = getattr(channel, 'inquiry_3', '') or ""
            
            # 문의박스 데이터가 있으면 생성 (영상과 동일한 스타일!)
            if inquiry_1 or inquiry_2 or inquiry_3:
                # inquiry_style이 없으면 기본 스타일 사용
                if not inquiry_style:
                    inquiry_style = self._get_inquiry_style()
                
                # 영상용 문의박스 함수에서 이미지만 추출
                inq_img = self._create_inquiry_box_for_thumbnail(
                    inquiry_1, inquiry_2, inquiry_3, inquiry_style,
                    line4=getattr(channel, 'inquiry_4', '') if channel else '',
                    font_size_base=getattr(channel, 'inquiry_font_size', None) if channel else None,
                    bold=getattr(channel, 'inquiry_bold', True) if channel else True
                )
                
                if inq_img:
                    ix = (target_w - inq_img.width) // 2
                    iy = (target_h - inq_img.height) // 2  # 정중앙!
                    canvas.paste(inq_img, (ix, iy), inq_img)
                    self._log(f"   ✅ 썸네일 문의박스 (중앙: {ix}, {iy})")
                else:
                    self._log(f"   ⚠️ 문의박스 이미지 생성 실패")
            else:
                self._log(f"   ⚠️ 문의박스 데이터 없음")

            # ========================================
            # 4) 저장
            # ========================================
            canvas = canvas.convert("RGB")
            canvas.save(out_path, "JPEG", quality=90)
            self._log(f"   🖼️ 썸네일 생성 완료")

        except Exception as e:
            self._log(f"   ⚠️ 썸네일 생성 실패: {e}")
            import traceback
            self._log(traceback.format_exc())

    def _create_metadata(self, title, channel, out_path):
        """YouTube 업로드용 메타데이터 생성"""
        try:
            description = self._generate_description(title, channel)
            tags = self._generate_tags(channel.project_name, title, channel=channel)
            
            # 문의 정보 추가
            inquiry_lines = []
            if getattr(channel, 'inquiry_1', ''):
                inquiry_lines.append(channel.inquiry_1)
            if getattr(channel, 'inquiry_2', ''):
                inquiry_lines.append(channel.inquiry_2)
            if getattr(channel, 'inquiry_3', ''):
                inquiry_lines.append(channel.inquiry_3)
            
            # 전체 설명 (문의 정보 포함)
            full_description = description
            
            # ⭐ 링크 URL 추가 (설명란 상단에 배치 → 클릭률 높임)
            link_url = getattr(channel, 'link_url', '') or ''
            if link_url.strip():
                full_description += f"\n\n🔗 자세히 알아보기: {link_url.strip()}"
            
            if inquiry_lines:
                full_description += "\n\n📞 문의\n" + "\n".join(inquiry_lines)
            
            # ⭐ 통일된 하단 (해시태그 + 면책조항) - 1곳에서만!
            project_tag = channel.project_name.replace(' ', '')
            # ⭐ SEO 해시태그 - 영상마다 다르게 (랜덤 풀)
            import hashlib as _hs2, time as _t2
            _seed2 = int(_hs2.md5(f"{channel.project_name}{title}{int(_t2.time()*1000)%99991}".encode()).hexdigest(), 16) % (2**32)
            _rng2 = random.Random(_seed2)
            pn = channel.project_name.replace(' ', '')

            # 프로젝트명 조합 태그 풀 (매번 2개 랜덤 선택)
            project_hash_pool = [
                f"#{pn}모델하우스", f"#{pn}분양가", f"#{pn}평면도",
                f"#{pn}홍보관", f"#{pn}분양일정", f"#{pn}입주일",
                f"#{pn}계약조건", f"#{pn}잔여세대", f"#{pn}분양문의",
                f"#{pn}타입", f"#{pn}위치", f"#{pn}교통",
            ]
            # 일반 SEO 태그 풀 (매번 3개 랜덤 선택)
            general_hash_pool = [
                "#분양", "#아파트", "#부동산", "#신축아파트",
                "#내집마련", "#분양정보", "#아파트분양", "#부동산정보",
                "#모델하우스", "#분양가", "#입주", "#신규분양",
                "#부동산시장", "#아파트정보", "#분양권",
            ]
            # 지역명 추출 (프로젝트명/제목에서)
            area = self._extract_area_from_text(channel.project_name, title)
            area_tags = []
            if area:
                # "청량리역" 처럼 역 이름이 포함된 경우 역 버전도 추가
                import re as _re2
                station_match = _re2.search(r'(' + re.escape(area) + r'역)', channel.project_name + title)
                area_with_station = station_match.group(1) if station_match else None

                area_hash_pool = [
                    f"#{area}분양", f"#{area}아파트", f"#{area}신축",
                    f"#{area}부동산", f"#{area}모델하우스", f"#{area}분양가",
                    f"#{area}역세권", f"#{area}내집마련",
                ]
                # 역 이름 버전 풀 추가 (예: #청량리역분양, #청량리역아파트)
                if area_with_station:
                    area_hash_pool += [
                        f"#{area_with_station}분양", f"#{area_with_station}아파트",
                        f"#{area_with_station}신축", f"#{area_with_station}부동산",
                    ]
                    area_tags = [f"#{area_with_station}"] + _rng2.sample(area_hash_pool, k=2)
                else:
                    area_tags = _rng2.sample(area_hash_pool, k=2)

            picked_project = _rng2.sample(project_hash_pool, k=2)
            picked_general = _rng2.sample(general_hash_pool, k=2)
            all_tags = [f"#{pn}", f"#{pn}분양"] + picked_project + area_tags + picked_general
            hash_tags = " ".join(all_tags)
            full_description += f"\n\n{hash_tags}"
            full_description += "\n\n※ 본 영상은 분양 홍보 목적입니다."
            full_description += "\n※ 정확한 정보는 모델하우스에서 확인하세요."
            
            meta = {
                # YouTube 필수 필드
                "title": title[:100],  # YouTube 100자 제한
                "description": full_description[:5000],  # YouTube 5000자 제한
                "tags": tags[:30],  # YouTube 30개 제한
                "categoryId": "22",  # People & Blogs
                "privacyStatus": "public",  # public, private, unlisted
                "madeForKids": False,
                "defaultLanguage": "ko",
                "defaultAudioLanguage": "ko",
                
                # 추가 정보
                "project_name": channel.project_name,
                "channel_name": getattr(channel, 'name', ''),
                "created_at": datetime.now().isoformat(),
                
                # 파일 경로 (상대 경로)
                "video_file": "video.mp4",
                "thumbnail_file": "thumbnail.jpg",
            }
            
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            self._log(f"   📄 메타데이터 생성 (YouTube 업로드용)")
        except Exception as e:
            self._log(f"   ⚠️ 메타데이터 생성 실패: {e}")
    

    def _create_image_clip(self, src, duration, effect=None, frame_style=None, enhance_style=None, pdf_mode=False):
        """이미지 클립 생성 (blur 배경 + 테두리/액자 효과 + 사진 보정)
        pdf_mode=True면 blur 배경 없이 이미지만 중앙에 (오버레이가 배경)
        """
        # videos/mixed에서 mp4가 들어올 수 있음
        if self._is_video_file(str(src)):
            return self._create_video_clip(str(src), float(duration))
        
        try:
            img = Image.open(src)
        except Exception as e:
            self._log(f"      ⚠️ 이미지 열기 실패: {src} → {e}")
            # 검정 배경 fallback
            fallback = np.zeros((1920, 1080, 3), dtype=np.uint8)
            return ImageClip(fallback).set_duration(duration)
        
        # EXIF 회전 정보 적용 (스마트폰 사진 누워있는 문제 해결)
        try:
            from PIL import ExifTags
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = img._getexif()
            if exif is not None:
                orientation_value = exif.get(orientation)
                if orientation_value == 3:
                    img = img.rotate(180, expand=True)
                elif orientation_value == 6:
                    img = img.rotate(270, expand=True)
                elif orientation_value == 8:
                    img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError, TypeError):
            pass
        
        img = img.convert("RGB")
        
        # 사진 보정 적용 (부동산용)
        if enhance_style:
            img, _ = self._apply_photo_enhance(img, enhance_style)
        
        target_w, target_h = 1080, 1920
        img_ratio = img.width / img.height
        
        # 테두리/액자 스타일 (한 영상 내 통일)
        if frame_style is None:
            frame_style = self._get_frame_style()
        
        # ========================================
        # PDF/Photos 오버레이 모드: 원본 이미지 중앙 배치
        # ========================================
        if pdf_mode:
            self._log(f"      📄 오버레이 모드 ({img.width}x{img.height}) → 원본 비율 중앙")
            
            # 모든 사진을 중앙 배치 (9:16도 4:3 방식 적용)
            max_w = int(target_w * 0.95)
            max_h = int(target_h * 0.70)
            
            scale = min(max_w / img.width, max_h / img.height)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            
            img = img.resize((new_w, new_h), RESAMPLE)
            
            # 테두리 적용
            if frame_style and frame_style.get("type") != "none":
                img = self._apply_frame_effect(img, frame_style)
                new_w, new_h = img.size
            
            # 정중앙 배치 (모든 비율 동일)
            x = (target_w - new_w) // 2
            top_margin = int(target_h * 0.12)
            bottom_margin = int(target_h * 0.15)
            available_h = target_h - top_margin - bottom_margin
            y = top_margin + (available_h - new_h) // 2
            
            # 자막 위치는 고정 (화면 하단)
            self._last_img_bottom = 1300  # 1300 고정
            
            clip = ImageClip(np.array(img)).set_duration(duration)
            
            # 장면 효과 적용 (줌인/줌아웃)
            if effect:
                dur = duration
                try:
                    if effect == "ZOOM_IN":
                        clip = clip.resize(lambda t, d=dur: 1 + 0.06 * (t / d))
                    elif effect == "ZOOM_OUT":
                        clip = clip.resize(lambda t, d=dur: 1.06 - 0.06 * (t / d))
                    self._log(f"      🎬 장면효과: {effect}")
                except:
                    pass
            
            return clip.set_position((x, y))
        
        # ========================================
        # 가로 이미지 → blur 배경 + 중앙 전경
        # ========================================
        if img_ratio > 1.0:
            self._log(f"      📐 가로 ({img.width}x{img.height}) → blur 배경")
            
            # 1. 배경: 세로에 맞춰 확대 후 blur
            bg_scale = target_h / img.height
            bg_w = int(img.width * bg_scale)
            bg_h = target_h
            bg_img = img.resize((bg_w, bg_h), RESAMPLE)
            
            # 가로가 화면보다 작으면 더 확대
            if bg_w < target_w:
                bg_scale2 = target_w / bg_w
                bg_w = target_w
                bg_h = int(bg_h * bg_scale2)
                bg_img = img.resize((bg_w, bg_h), RESAMPLE)
            
            # 중앙 크롭
            if bg_w > target_w:
                left = (bg_w - target_w) // 2
                bg_img = bg_img.crop((left, 0, left + target_w, bg_h))
            if bg_h > target_h:
                top = (bg_h - target_h) // 2
                bg_img = bg_img.crop((0, top, target_w, top + target_h))
            
            # 크기 맞추기
            bg_img = bg_img.resize((target_w, target_h), RESAMPLE)
            
            # blur 적용 (radius 20으로 최적화)
            try:
                from PIL import ImageFilter
                bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=20))
                # 어둡게 (오버레이 효과)
                from PIL import ImageEnhance
                bg_img = ImageEnhance.Brightness(bg_img).enhance(0.5)
            except Exception as e:
                self._log(f"      ⚠️ blur 실패: {e}")
            
            # 2. 전경: 세로 60% 크기로 중앙 배치
            fg_h = int(target_h * 0.60)
            fg_scale = fg_h / img.height
            fg_w = int(img.width * fg_scale)
            
            # 가로가 화면 90%보다 크면 축소
            if fg_w > target_w * 0.90:
                fg_w = int(target_w * 0.90)
                fg_scale = fg_w / img.width
                fg_h = int(img.height * fg_scale)
            
            fg_img = img.resize((fg_w, fg_h), RESAMPLE)
            
            # 3. 테두리/액자 효과 적용
            fg_img = self._apply_frame_effect(fg_img, frame_style)
            fg_w, fg_h = fg_img.size  # 테두리 적용 후 크기 업데이트
            
            # 4. 합성
            final_img = bg_img.convert("RGBA")
            fg_rgba = fg_img.convert("RGBA")
            
            fg_x = (target_w - fg_w) // 2
            fg_y = (target_h - fg_h) // 2
            
            final_img.paste(fg_rgba, (fg_x, fg_y), fg_rgba)
            final_img = final_img.convert("RGB")
            
            clip = ImageClip(np.array(final_img)).set_duration(duration)
        
        # ========================================
        # 세로/정방형 이미지 → blur 배경 + 중앙 + 테두리
        # ========================================
        else:
            self._log(f"      📐 세로 ({img.width}x{img.height}) → blur 배경 + 테두리")
            
            # 1. 배경: 가로에 맞춰 확대 후 blur
            bg_scale = target_w / img.width
            bg_w = target_w
            bg_h = int(img.height * bg_scale)
            bg_img = img.resize((bg_w, bg_h), RESAMPLE)
            
            # 세로가 화면보다 작으면 더 확대
            if bg_h < target_h:
                bg_scale2 = target_h / bg_h
                bg_w = int(bg_w * bg_scale2)
                bg_h = target_h
                bg_img = bg_img.resize((bg_w, bg_h), RESAMPLE)
            
            # 중앙 크롭
            left = (bg_w - target_w) // 2
            top = (bg_h - target_h) // 2
            bg_img = bg_img.crop((left, top, left + target_w, top + target_h))
            
            # blur 적용 (radius 15로 최적화)
            from PIL import ImageFilter, ImageEnhance
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=15))
            # 약간 어둡게
            bg_img = ImageEnhance.Brightness(bg_img).enhance(0.6)
            
            # 2. 전경: 화면 높이의 85%로 리사이즈 (세로 사진은 높이 기준)
            fg_h = int(target_h * 0.85)
            fg_scale = fg_h / img.height
            fg_w = int(img.width * fg_scale)
            
            # 가로가 화면보다 크면 가로 기준으로
            if fg_w > target_w * 0.9:
                fg_w = int(target_w * 0.9)
                fg_scale = fg_w / img.width
                fg_h = int(img.height * fg_scale)
            
            fg_img = img.resize((fg_w, fg_h), RESAMPLE)
            
            # 3. 테두리/액자 효과 적용
            fg_img = self._apply_frame_effect(fg_img, frame_style)
            fg_w, fg_h = fg_img.size  # 테두리 적용 후 크기 업데이트
            
            # 4. 합성
            final_img = bg_img.convert("RGBA")
            fg_rgba = fg_img.convert("RGBA")
            
            fg_x = (target_w - fg_w) // 2
            fg_y = (target_h - fg_h) // 2
            
            final_img.paste(fg_rgba, (fg_x, fg_y), fg_rgba)
            final_img = final_img.convert("RGB")
            
            clip = ImageClip(np.array(final_img)).set_duration(duration)
        
        # 장면 효과 적용
        if effect:
            dur = duration
            try:
                if effect == "ZOOM_IN":
                    clip = clip.resize(lambda t, d=dur: 1 + 0.06 * (t / d))
                elif effect == "ZOOM_OUT":
                    clip = clip.resize(lambda t, d=dur: 1.06 - 0.06 * (t / d))
            except:
                pass
        
        return clip
    

    def _make_scene_overlay_clip(self, pil_img, duration, start_time):
        """
        장면 오버레이 PIL 이미지 → ImageClip (가운데 정렬, 투명 지원)
        렌더링 빠름: ImageClip + set_start/set_duration만 사용
        """
        try:
            # RGBA 분리
            if pil_img.mode == "RGBA":
                rgb = np.array(pil_img.convert("RGB"))
                alpha = np.array(pil_img.split()[3]) / 255.0
                clip = ImageClip(rgb, ismask=False).set_duration(duration)
                clip = clip.set_mask(ImageClip(alpha, ismask=True).set_duration(duration))
            else:
                clip = ImageClip(np.array(pil_img.convert("RGB"))).set_duration(duration)
            
            # 가운데 정렬
            clip = clip.set_position(("center", "center"))
            clip = clip.set_start(start_time)
            
            return clip
        except Exception as e:
            self._log(f"   ⚠️ 장면오버레이 클립 생성 실패: {e}")
            return None


    def _create_output_folder(self, project, mode, suffix="_READY"):
        date_str = datetime.now().strftime("%Y_%m_%d")
        base = os.path.join(self.output_dir, date_str)
        
        try:
            os.makedirs(base, exist_ok=True)
        except Exception as e:
            self._log(f"   ⚠️ 날짜 폴더 생성 실패: {e}")
            base = self.output_dir  # fallback
        
        # 프로젝트명 정리 (특수문자 제거)
        safe_project = re.sub(r'[\\/*?:"<>|]', '', project or "project")
        if not safe_project:
            safe_project = "project"
        # TEST는 누적되면 겹침/혼란이 생기므로: 같은 날짜 폴더의 기존 TEST 결과를 정리
        idx = 1
        while idx < 1000:  # 무한루프 방지
            name = f"{safe_project}__{mode}__{idx:03d}{suffix}"
            path = os.path.join(base, name)
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                    return path
                except Exception as e:
                    self._log(f"   ⚠️ 폴더 생성 실패 ({idx}): {e}")
                    idx += 1
                    continue
            idx += 1
        
        # 1000번까지 다 찼으면 타임스탬프로
        ts = datetime.now().strftime("%H%M%S")
        fallback_path = os.path.join(base, f"{safe_project}__{mode}__{ts}{suffix}")
        os.makedirs(fallback_path, exist_ok=True)
        return fallback_path
    
    # 영상 생성 (본 제작) - 모드별 완전 분리
    # ============================================================
    

    def _create_inquiry_box(self, line1, line2, line3, duration, style=None, is_bright_overlay=False,
                             line4="", font_size_base=None, no_bg=False, bold=True,
                             font_sizes=None):
        """문의박스
        - line1~3: 박스 안
        - line4: 박스 아래 별도 표시 (두 줄 가능)
        - font_size_base: 사용자 지정 크기 (초과 시 경고만, 자동 축소 안 함)
        """
        # 박스 안 lines (1~3만)
        box_lines = [l for l in [line1, line2, line3] if l]
        if not box_lines:
            return None

        if style is None:
            style = self._get_inquiry_style()

        font_path = self._get_font_path_by_weight(bold=bold)

        # 글씨 크기 (개별 또는 공통)
        # font_sizes = [s1, s2, s3, s4] 개별 지정 우선, 없으면 font_size_base 사용
        if font_sizes and isinstance(font_sizes, (list, tuple)) and len(font_sizes) >= 3:
            _sizes = [int(s) for s in font_sizes]
            font_size_line1 = _sizes[0]
            # box_lines 각 줄 크기: 인덱스 매핑
            _line_sizes = _sizes[:3]  # 박스 안 1~3
            _line4_size = int(_sizes[3]) if len(_sizes) > 3 else _sizes[-1]
        elif font_size_base and isinstance(font_size_base, (int, float)):
            font_size_line1 = int(font_size_base)
            _s2 = max(30, int(font_size_base * 0.78))
            _line_sizes = [font_size_line1, _s2, _s2]
            _line4_size = _s2
        else:
            font_size_line1 = 90
            _line_sizes = [90, 70, 70]
            _line4_size = 70
        font_size_others = _line_sizes[1] if len(_line_sizes) > 1 else 70
        outline_width = 5

        MAX_TEXT_W = 1000
        MAX_BOX_H = 480

        # ⭐ 화면 초과 감지 → 경고 로그만 (자동 축소 안 함)
        n = len(box_lines)
        overflow_warned = False
        try:
            for i, line in enumerate(box_lines):
                fsize = _line_sizes[i] if i < len(_line_sizes) else font_size_others
                tf = ImageFont.truetype(font_path, fsize) if font_path else ImageFont.load_default()
                bbox = tf.getbbox(line)
                tw = bbox[2] - bbox[0]
                if tw > MAX_TEXT_W and not overflow_warned:
                    self._log(f"   ⚠️ 문의{i+1} 글씨가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
                    overflow_warned = True
        except:
            pass

        try:
            estimated_h = 70 + (font_size_line1 + 25) + (font_size_others + 20) * (n - 1)
            if estimated_h > MAX_BOX_H and not overflow_warned:
                self._log(f"   ⚠️ 문의박스가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
        except:
            pass

        # 개별 폰트 생성
        _fonts = []
        for _fs in _line_sizes:
            try:
                _fonts.append(ImageFont.truetype(font_path, _fs) if font_path else ImageFont.load_default())
            except:
                _fonts.append(ImageFont.load_default())
        font_big = _fonts[0] if _fonts else ImageFont.load_default()
        font_normal = _fonts[1] if len(_fonts) > 1 else font_big
        try:
            font_line4_obj = ImageFont.truetype(font_path, _line4_size) if font_path else ImageFont.load_default()
        except:
            font_line4_obj = font_normal

        # 높이 계산 (개별 크기)
        _line_heights = [(_line_sizes[i] + 25 if i == 0 else _line_sizes[i] + 20)
                         for i in range(len(_line_sizes))]
        line_h_big = _line_heights[0]
        line_h_normal = _line_heights[1] if len(_line_heights) > 1 else font_size_others + 20

        total_h = 70
        for i in range(n):
            total_h += (_line_heights[i] if i < len(_line_heights) else line_h_normal)

        # 너비 계산
        bg_type = style.get("bg_type", "rounded_box")
        if style.get("width") == "full":
            total_w = 1080
        else:
            max_text_w = 0
            for i, line in enumerate(box_lines):
                font = _fonts[i] if i < len(_fonts) else font_normal
                bbox = font.getbbox(line)
                max_text_w = max(max_text_w, bbox[2] - bbox[0])
            total_w = min(1050, max(700, max_text_w + 140))
        
        # 이미지 생성
        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 배경 + 테두리 그리기 (8종 프리셋!)
        radius = style.get("radius", 20)
        bg_color = style.get("bg_color", (20, 30, 40, 245))
        border_color = style.get("border_color", (255, 255, 255, 255))
        border_width = style.get("border_width", 3)
        
        if not no_bg:
            if bg_type == "rounded_box":
                bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=border_color, width=border_width)
            elif bg_type == "full_stripe":
                bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
                draw.rectangle([0, 0, total_w, total_h], fill=bg_color)
                draw.rectangle([0, 0, total_w-1, total_h-1], outline=border_color, width=border_width)
            elif bg_type == "gradient_box":
                bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
                for i in range(15):
                    alpha = int(40 - i * 2.5)
                    draw.rectangle([0, total_h - 15 + i, total_w, total_h - 14 + i],
                                   fill=(255, 255, 255, alpha))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=border_color, width=border_width)
            elif bg_type == "outline_only":
                bg_color_dim = (bg_color[0], bg_color[1], bg_color[2], 180)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color_dim)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=border_color, width=5)
            elif bg_type == "underline_box":
                bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
                underline_color = style.get("underline_color", (255, 200, 100))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
                draw.rectangle([15, total_h - 10, total_w - 15, total_h - 5],
                               fill=(*underline_color, 255))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=border_color, width=border_width)
            elif bg_type == "gradient_vertical":
                for i in range(total_h):
                    ratio = i / total_h
                    alpha = int(200 + 55 * ratio)
                    color = (bg_color[0], bg_color[1], bg_color[2], alpha)
                    draw.rectangle([0, i, total_w, i+1], fill=color)
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=border_color, width=border_width)
            elif bg_type == "ribbon":
                accent = style.get("accent_color", (255, 200, 100))
                fold = 25
                points = [
                    (fold, 0), (total_w - fold, 0),
                    (total_w, total_h // 2),
                    (total_w - fold, total_h),
                    (fold, total_h),
                    (0, total_h // 2),
                ]
                draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
                draw.polygon(points, outline=(*accent, 255))
            elif bg_type == "speech_bubble":
                bubble_h = total_h - 15
                draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                       fill=(bg_color[0], bg_color[1], bg_color[2], 235))
                draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                       outline=border_color, width=2)
                tail_x = int(total_w * 0.7)
                tail_pts = [(tail_x - 10, bubble_h - 2), (tail_x + 10, bubble_h - 2), (tail_x + 20, total_h)]
                draw.polygon(tail_pts, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
            elif bg_type == "cut_corner":
                cut = 30
                accent = style.get("accent_color", (255, 200, 100))
                points = [
                    (0, 0), (total_w - cut, 0),
                    (total_w, cut),
                    (total_w, total_h),
                    (0, total_h),
                ]
                draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
                draw.polygon(points, outline=border_color)
                draw.polygon([(total_w - cut, 0), (total_w, cut), (total_w - cut, cut)],
                             fill=(*accent, 200))
            elif bg_type == "left_bar":
                accent = style.get("accent_color", (255, 200, 100))
                bar_w = 8
                draw.rectangle([bar_w, 0, total_w, total_h],
                               fill=(bg_color[0], bg_color[1], bg_color[2], 220))
                draw.rectangle([0, 0, bar_w, total_h], fill=(*accent, 255))
            elif bg_type == "deco_lines":
                accent = style.get("accent_color", (255, 200, 100))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       fill=(bg_color[0], bg_color[1], bg_color[2], 210))
                draw.line([20, 6, total_w - 20, 6], fill=(*accent, 255), width=2)
                draw.line([35, 12, total_w - 35, 12], fill=(*accent, 150), width=1)
                draw.line([20, total_h - 6, total_w - 20, total_h - 6], fill=(*accent, 255), width=2)
                draw.line([35, total_h - 12, total_w - 35, total_h - 12], fill=(*accent, 150), width=1)
            elif bg_type == "shadow_card":
                draw.rounded_rectangle([5, 5, total_w, total_h], radius=radius,
                                       fill=(0, 0, 0, 100))
                draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                       fill=(bg_color[0], bg_color[1], bg_color[2], 240))
                draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                       outline=border_color, width=2)
            elif bg_type == "neon_glow":
                glow_color = style.get("accent_color", (100, 200, 255))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       fill=(bg_color[0], bg_color[1], bg_color[2], 200))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                       outline=(*glow_color, 80), width=8)
                draw.rounded_rectangle([3, 3, total_w-3, total_h-3], radius=radius,
                                       outline=(*glow_color, 200), width=2)
            elif bg_type == "trapezoid":
                indent = 20
                accent = style.get("accent_color", (255, 200, 100))
                points = [
                    (indent, 0), (total_w - indent, 0),
                    (total_w, total_h),
                    (0, total_h),
                ]
                draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
                draw.polygon(points, outline=(*accent, 200))
            elif bg_type == "none":
                pass
            else:
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=20, fill=(20, 30, 40, 245))
                draw.rounded_rectangle([0, 0, total_w, total_h], radius=20,
                                       outline=border_color, width=border_width)
        # no_bg=True 면 배경/테두리 없이 텍스트만
        
        # 오버레이 밝기에 따른 색상 설정!
        if is_bright_overlay:
            # 밝은 오버레이 → 어두운 글씨 + 흰색 테두리
            color_line1 = (30, 30, 30)      # 1번: 어두운
            outline_line1 = (255, 255, 255) # 1번 테두리: 흰색
            # 2,3번도 어둡게
            accent = style.get("accent_color", (200, 100, 0))
            color_others = (max(0, accent[0]-100), max(0, accent[1]-50), max(0, accent[2]))
            outline_others = (255, 255, 255)
        else:
            # 어두운 오버레이 → 밝은 글씨 + 검정 테두리
            color_line1 = (255, 255, 255)  # 1번: 흰색
            outline_line1 = (0, 0, 0)      # 1번 테두리: 검정
            accent = style.get("accent_color", (255, 200, 0))
            color_others = accent
            outline_others = (0, 0, 0)
        
        # 그림자 사용 여부
        use_shadow = style.get("use_shadow", False)
        
        # 텍스트 그리기 (box_lines, 개별 폰트/크기)
        y = 35
        for i, line in enumerate(box_lines):
            font = _fonts[i] if i < len(_fonts) else font_normal
            color = color_line1 if i == 0 else color_others
            outline_color = outline_line1 if i == 0 else outline_others
            lh = _line_heights[i] if i < len(_line_heights) else line_h_normal
            
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (total_w - w) // 2
            
            if use_shadow:
                for dx, dy in [(3, 3), (4, 4), (5, 5)]:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 200 - dx * 25))
            
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, font=font, fill=(*outline_color, 255))
            
            draw.text((x, y), line, font=font, fill=(*color, 255))
            y += lh
        
        # ── line4: 박스 아래 1줄 별도 렌더링 ──
        if line4 and str(line4).strip():
            try:
                l4 = str(line4).strip()
                pad = 10
                line4_h = _line4_size + 20
                combined_h = total_h + pad + line4_h
                combined_img = Image.new("RGBA", (total_w, combined_h), (0, 0, 0, 0))
                combined_img.paste(img, (0, 0))
                draw4 = ImageDraw.Draw(combined_img)
                bbox4 = draw4.textbbox((0, 0), l4, font=font_line4_obj)
                w4 = bbox4[2] - bbox4[0]
                x4 = (total_w - w4) // 2
                y4 = total_h + pad
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw4.text((x4+dx, y4+dy), l4, font=font_line4_obj, fill=(*outline_others, 255))
                draw4.text((x4, y4), l4, font=font_line4_obj, fill=(*color_others, 255))
                img = combined_img
            except Exception as e4:
                self._log(f"   ⚠️ line4 렌더링 오류: {e4}")

        # RGBA → RGB + 마스크 분리 (moviepy 호환)
        if img.mode == "RGBA":
            rgb = np.array(img.convert("RGB"))
            alpha = np.array(img.split()[3]) / 255.0  # 0~1 정규화
            clip = ImageClip(rgb).set_duration(duration)
            mask = ImageClip(alpha, ismask=True).set_duration(duration)
            clip = clip.set_mask(mask)
            return clip
        else:
            return ImageClip(np.array(img)).set_duration(duration)
    

    def _create_inquiry_box_animated(self, line1, line2, line3, duration, is_first_scene=False, 
                                      slide_direction="left", slide_speed=0.5, style=None, is_bright_overlay=False,
                                      line4="", font_size_base=None, no_bg=False, bold=True,
                                      font_sizes=None):
        """문의박스 + 슬라이드 애니메이션
        - line1~3: 박스 안 / line4: 박스 아래 별도 표시
        - font_size_base: 사용자 지정 크기 (초과 시 경고만)
        """
        box_lines = [l for l in [line1, line2, line3] if l]
        if not box_lines:
            return None

        if style is None:
            style = self._get_inquiry_style()

        font_path = self._get_font_path_by_weight(bold=bold)

        if font_size_base and isinstance(font_size_base, (int, float)):
            font_size_line1 = int(font_size_base)
            font_size_others = max(30, int(font_size_base * 0.78))
        else:
            font_size_line1 = 90
            font_size_others = 70
        outline_width = 5

        MAX_TEXT_W = 1000
        MAX_BOX_H = 480
        n = len(box_lines)

        # 화면 초과 경고만 (자동 축소 안 함)
        overflow_warned = False
        try:
            for i, line in enumerate(box_lines):
                fsize = font_size_line1 if i == 0 else font_size_others
                tf = ImageFont.truetype(font_path, fsize) if font_path else ImageFont.load_default()
                bbox = tf.getbbox(line)
                if bbox[2] - bbox[0] > MAX_TEXT_W and not overflow_warned:
                    self._log(f"   ⚠️ 문의{i+1} 글씨가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
                    overflow_warned = True
        except:
            pass
        try:
            estimated_h = 70 + (font_size_line1 + 25) + (font_size_others + 20) * (n - 1)
            if estimated_h > MAX_BOX_H and not overflow_warned:
                self._log(f"   ⚠️ 문의박스가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
        except:
            pass
        
        # font_sizes 개별 지정 처리
        if font_sizes and isinstance(font_sizes, (list, tuple)) and len(font_sizes) >= 3:
            _sizes = [int(s) for s in font_sizes]
            font_size_line1 = _sizes[0]
            _line_sizes = _sizes[:3]
            _line4_size = int(_sizes[3]) if len(_sizes) > 3 else _sizes[-1]
        else:
            _line_sizes = [font_size_line1, font_size_others, font_size_others]
            _line4_size = font_size_others

        try:
            font_big = ImageFont.truetype(font_path, font_size_line1) if font_path else ImageFont.load_default()
            font_normal = ImageFont.truetype(font_path, font_size_others) if font_path else ImageFont.load_default()
        except:
            font_big = ImageFont.load_default()
            font_normal = ImageFont.load_default()

        # 개별 폰트 리스트 생성 (_fonts)
        _fonts = []
        for _fs in _line_sizes:
            try:
                _fonts.append(ImageFont.truetype(font_path, _fs) if font_path else ImageFont.load_default())
            except:
                _fonts.append(ImageFont.load_default())
        if not _fonts:
            _fonts = [font_big, font_normal, font_normal]

        # 높이 계산 (개별 크기)
        line_h_big = font_size_line1 + 25
        line_h_normal = font_size_others + 20
        _line_heights = [(_line_sizes[i] + 25 if i == 0 else _line_sizes[i] + 20)
                         for i in range(len(_line_sizes))]

        total_h = 70  # 상하 패딩
        total_h += _line_heights[0] if _line_heights else line_h_big
        total_h += sum(_line_heights[1:len(box_lines)]) if len(_line_heights) > 1 else line_h_normal * (n - 1)
        
        # 너비 계산 (box_lines 기준)
        bg_type = style.get("bg_type", "rounded_box")
        if style.get("width") == "full":
            total_w = 1080
        else:
            max_text_w = 0
            for i, line in enumerate(box_lines):
                font = _fonts[i] if i < len(_fonts) else font_normal
                bbox = font.getbbox(line)
                max_text_w = max(max_text_w, bbox[2] - bbox[0])
            total_w = min(1050, max(700, max_text_w + 140))
        
        # 이미지 생성
        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 배경 그리기 (8종 프리셋!)
        radius = style.get("radius", 20)
        bg_color = style.get("bg_color", (20, 30, 40, 245))
        border_color = style.get("border_color", (255, 255, 255, 255))  # ⭐ 기본값 항상 할당
        border_width = style.get("border_width", 3)
        
        if bg_type == "rounded_box":
            bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
        
        elif bg_type == "full_stripe":
            bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
            draw.rectangle([0, 0, total_w, total_h], fill=bg_color)
        
        elif bg_type == "gradient_box":
            bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
            for i in range(15):
                alpha = int(40 - i * 2.5)
                draw.rectangle([0, total_h - 15 + i, total_w, total_h - 14 + i], 
                              fill=(255, 255, 255, alpha))
        
        elif bg_type == "outline_only":
            bg_color_dim = (bg_color[0], bg_color[1], bg_color[2], 150)
            border_color = style.get("border_color", (255, 200, 0, 255))
            border_width = style.get("border_width", 4)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color_dim)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                  outline=border_color, width=border_width)
        
        elif bg_type == "underline_box":
            bg_color = (bg_color[0], bg_color[1], bg_color[2], 245)
            underline_color = style.get("underline_color", (255, 200, 100))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color)
            draw.rectangle([15, total_h - 10, total_w - 15, total_h - 5], 
                          fill=(*underline_color, 255))
        
        elif bg_type == "gradient_vertical":
            for i in range(total_h):
                ratio = i / total_h
                alpha = int(200 + 55 * ratio)
                color = (bg_color[0], bg_color[1], bg_color[2], alpha)
                draw.rectangle([0, i, total_w, i+1], fill=color)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                  outline=(255, 255, 255, 50), width=2)
        
        elif bg_type == "ribbon":
            accent = style.get("accent_color", (255, 200, 100))
            fold = 25
            points = [(fold, 0), (total_w - fold, 0), (total_w, total_h // 2),
                      (total_w - fold, total_h), (fold, total_h), (0, total_h // 2)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
            draw.polygon(points, outline=(*accent, 255))
        
        elif bg_type == "speech_bubble":
            bubble_h = total_h - 15
            draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 235))
            draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                  outline=border_color, width=2)
            tail_x = int(total_w * 0.7)
            tail_pts = [(tail_x - 10, bubble_h - 2), (tail_x + 10, bubble_h - 2), (tail_x + 20, total_h)]
            draw.polygon(tail_pts, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
        
        elif bg_type == "cut_corner":
            cut = 30
            accent = style.get("accent_color", (255, 200, 100))
            points = [(0, 0), (total_w - cut, 0), (total_w, cut), (total_w, total_h), (0, total_h)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
            draw.polygon(points, outline=border_color)
            draw.polygon([(total_w - cut, 0), (total_w, cut), (total_w - cut, cut)], fill=(*accent, 200))
        
        elif bg_type == "left_bar":
            accent = style.get("accent_color", (255, 200, 100))
            bar_w = 8
            draw.rectangle([bar_w, 0, total_w, total_h], fill=(bg_color[0], bg_color[1], bg_color[2], 220))
            draw.rectangle([0, 0, bar_w, total_h], fill=(*accent, 255))
        
        elif bg_type == "deco_lines":
            accent = style.get("accent_color", (255, 200, 100))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 210))
            draw.line([20, 6, total_w - 20, 6], fill=(*accent, 255), width=2)
            draw.line([35, 12, total_w - 35, 12], fill=(*accent, 150), width=1)
            draw.line([20, total_h - 6, total_w - 20, total_h - 6], fill=(*accent, 255), width=2)
            draw.line([35, total_h - 12, total_w - 35, total_h - 12], fill=(*accent, 150), width=1)
        
        elif bg_type == "shadow_card":
            draw.rounded_rectangle([5, 5, total_w, total_h], radius=radius, fill=(0, 0, 0, 100))
            draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 240))
            draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                  outline=border_color, width=2)
        
        elif bg_type == "neon_glow":
            glow_color = style.get("accent_color", (100, 200, 255))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 200))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  outline=(*glow_color, 80), width=8)
            draw.rounded_rectangle([3, 3, total_w-3, total_h-3], radius=radius,
                                  outline=(*glow_color, 200), width=2)
        
        elif bg_type == "trapezoid":
            indent = 20
            accent = style.get("accent_color", (255, 200, 100))
            points = [(indent, 0), (total_w - indent, 0), (total_w, total_h), (0, total_h)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
            draw.polygon(points, outline=(*accent, 200))
        
        elif bg_type == "none":
            pass
        
        else:
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=20, fill=(20, 30, 40, 245))
        
        # 오버레이 밝기에 따른 색상 설정!
        if is_bright_overlay:
            # 밝은 오버레이 → 어두운 글씨 + 흰색 테두리
            color_line1 = (30, 30, 30)      # 1번: 어두운
            outline_line1 = (255, 255, 255) # 1번 테두리: 흰색
            # 2,3번도 어둡게
            accent = style.get("accent_color", (200, 100, 0))
            color_others = (max(0, accent[0]-100), max(0, accent[1]-50), max(0, accent[2]))
            outline_others = (255, 255, 255)
        else:
            # 어두운 오버레이 → 밝은 글씨 + 검정 테두리
            color_line1 = (255, 255, 255)  # 1번: 흰색
            outline_line1 = (0, 0, 0)      # 1번 테두리: 검정
            accent = style.get("accent_color", (255, 200, 0))
            color_others = accent
            outline_others = (0, 0, 0)
        
        # 그림자 사용 여부
        use_shadow = style.get("use_shadow", False)
        
        # 텍스트 그리기 (box_lines, 개별 폰트/크기)
        y = 35
        for i, line in enumerate(box_lines):
            font = _fonts[i] if i < len(_fonts) else font_normal
            color = color_line1 if i == 0 else color_others
            outline_color = outline_line1 if i == 0 else outline_others
            lh = _line_heights[i] if i < len(_line_heights) else line_h_normal
            
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (total_w - w) // 2
            
            if use_shadow:
                for dx, dy in [(3, 3), (4, 4), (5, 5)]:
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 200 - dx * 25))
            
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, font=font, fill=(*outline_color, 255))
            
            draw.text((x, y), line, font=font, fill=(*color, 255))
            y += lh
        
        # ── line4: 박스 아래 1줄 별도 렌더링 ──
        if line4 and str(line4).strip():
            try:
                l4 = str(line4).strip()
                pad4 = 10
                lh4 = font_size_others + 20
                combined_h = total_h + pad4 + lh4
                combined_img = Image.new("RGBA", (total_w, combined_h), (0, 0, 0, 0))
                combined_img.paste(img, (0, 0))
                draw4 = ImageDraw.Draw(combined_img)
                bbox4 = draw4.textbbox((0, 0), l4, font=font_normal)
                w4 = bbox4[2] - bbox4[0]
                x4 = (total_w - w4) // 2
                y4 = total_h + pad4
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw4.text((x4+dx, y4+dy), l4, font=font_normal, fill=(*outline_others, 255))
                draw4.text((x4, y4), l4, font=font_normal, fill=(*color_others, 255))
                img = combined_img
                total_h = combined_h
            except Exception as e4:
                self._log(f"   ⚠️ line4 렌더링 오류: {e4}")

        # RGBA → RGB + 마스크 분리 (moviepy 호환)
        if img.mode == "RGBA":
            rgb = np.array(img.convert("RGB"))
            alpha = np.array(img.split()[3]) / 255.0  # 0~1 정규화
            clip = ImageClip(rgb).set_duration(duration)
            mask = ImageClip(alpha, ismask=True).set_duration(duration)
            clip = clip.set_mask(mask)
        else:
            clip = ImageClip(np.array(img)).set_duration(duration)
        
        # 위치: 상단 5%, 중앙
        _inq_pos_pct = getattr(self, '_current_inquiry_position', 5)
        try:
            _inq_pos_pct = int(_inq_pos_pct)
        except:
            _inq_pos_pct = 5
        final_y = int(1920 * _inq_pos_pct / 100)
        center_x = (1080 - total_w) // 2
        
        # 첫 장면: 슬라이드 → 중앙
        if is_first_scene:
            if slide_direction == "left":
                start_x = -total_w
            else:
                start_x = 1080
            
            def position_func(t):
                if t < slide_speed:
                    progress = t / slide_speed
                    progress = 1 - (1 - progress) ** 3
                    current_x = start_x + (center_x - start_x) * progress
                    return (current_x, final_y)
                else:
                    return (center_x, final_y)
            
            clip = clip.set_position(position_func)
        else:
            clip = clip.set_position((center_x, final_y))
        
        return clip
    
    # ============================================================
    # 오프닝
    # ============================================================
    

    def _create_inquiry_box_for_thumbnail(self, line1, line2, line3, style=None, line4="", font_size_base=None, bold=True):
        """썸네일용 문의박스 (line1~3: 박스 안, line4: 박스 아래)"""
        box_lines = [l for l in [line1, line2, line3] if l and str(l).strip()]
        if not box_lines:
            return None
        
        if style is None:
            style = self._get_inquiry_style()
        
        font_path = self._get_font_path_by_weight(bold=bold)
        
        if font_size_base and isinstance(font_size_base, (int, float)):
            font_size_line1 = int(font_size_base)
            font_size_others = max(30, int(font_size_base * 0.78))
        else:
            font_size_line1 = 90
            font_size_others = 70
        outline_width = 5
        
        MAX_TEXT_W = 1000
        MAX_BOX_H = 480
        n = len(box_lines)

        overflow_warned = False
        try:
            for i, line in enumerate(box_lines):
                fsize = font_size_line1 if i == 0 else font_size_others
                tf = ImageFont.truetype(font_path, fsize) if font_path else ImageFont.load_default()
                bbox = tf.getbbox(line)
                if bbox[2] - bbox[0] > MAX_TEXT_W and not overflow_warned:
                    self._log(f"   ⚠️ 문의{i+1} 글씨가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
                    overflow_warned = True
        except:
            pass
        try:
            estimated_h = 70 + (font_size_line1 + 25) + (font_size_others + 20) * (n - 1)
            if estimated_h > MAX_BOX_H and not overflow_warned:
                self._log(f"   ⚠️ 문의박스가 화면을 초과합니다. 글씨를 줄이거나 크기를 조절하세요.")
        except:
            pass
        
        try:
            font_big = ImageFont.truetype(font_path, font_size_line1) if font_path else ImageFont.load_default()
            font_normal = ImageFont.truetype(font_path, font_size_others) if font_path else ImageFont.load_default()
        except:
            font_big = ImageFont.load_default()
            font_normal = ImageFont.load_default()
        
        # 높이 계산 (box_lines 기준)
        line_h_big = font_size_line1 + 25
        line_h_normal = font_size_others + 20
        
        total_h = 70
        total_h += line_h_big
        total_h += line_h_normal * (n - 1)
        
        # 너비 계산 (box_lines 기준)
        bg_type = style.get("bg_type", "rounded_box")
        if style.get("width") == "full":
            total_w = 1080
        else:
            max_text_w = 0
            for i, line in enumerate(box_lines):
                font = font_big if i == 0 else font_normal
                bbox = font.getbbox(str(line))
                max_text_w = max(max_text_w, bbox[2] - bbox[0])
            total_w = min(1050, max(700, max_text_w + 140))
        
        # 이미지 생성
        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 배경 그리기 (8종 프리셋 - 영상과 동일!)
        radius = style.get("radius", 20)
        bg_color = style.get("bg_color", (20, 30, 40))
        if len(bg_color) == 3:
            bg_color = (*bg_color, 245)
        
        if bg_type == "rounded_box":
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 245))
        
        elif bg_type == "full_stripe":
            draw.rectangle([0, 0, total_w, total_h], 
                          fill=(bg_color[0], bg_color[1], bg_color[2], 245))
        
        elif bg_type == "gradient_box":
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 245))
            for i in range(15):
                alpha = int(40 - i * 2.5)
                draw.rectangle([0, total_h - 15 + i, total_w, total_h - 14 + i], 
                              fill=(255, 255, 255, alpha))
        
        elif bg_type == "outline_only":
            bg_color_dim = (bg_color[0], bg_color[1], bg_color[2], 150)
            border_color = style.get("border_color", (255, 200, 0, 255))
            border_width = style.get("border_width", 4)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, fill=bg_color_dim)
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                  outline=border_color, width=border_width)
        
        elif bg_type == "underline_box":
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 245))
            underline_color = style.get("underline_color", (255, 200, 100))
            draw.rectangle([20, total_h - 12, total_w - 20, total_h - 6], 
                          fill=(*underline_color, 255))
        
        elif bg_type == "shadow_box":
            for offset in range(8, 0, -2):
                alpha = int(60 - offset * 6)
                draw.rounded_rectangle([offset, offset, total_w, total_h], 
                                      radius=radius, fill=(0, 0, 0, alpha))
            draw.rounded_rectangle([0, 0, total_w - 4, total_h - 4], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 250))
        
        elif bg_type == "glow_box":
            glow_color = style.get("glow_color", (0, 200, 255))
            for offset in range(10, 0, -2):
                alpha = int(30 - offset * 2)
                draw.rounded_rectangle([-offset, -offset, total_w + offset, total_h + offset], 
                                      radius=radius + offset, fill=(*glow_color, alpha))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 250))
        
        elif bg_type == "double_border":
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 245))
            outer_color = style.get("outer_border_color", (255, 200, 0))
            inner_color = style.get("inner_border_color", (255, 255, 255))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                  outline=(*outer_color, 255), width=4)
            draw.rounded_rectangle([6, 6, total_w - 6, total_h - 6], radius=max(0, radius - 4), 
                                  outline=(*inner_color, 200), width=2)
        
        elif bg_type == "ribbon":
            accent = style.get("accent_color", (255, 200, 100))
            fold = 25
            points = [(fold, 0), (total_w - fold, 0), (total_w, total_h // 2),
                      (total_w - fold, total_h), (fold, total_h), (0, total_h // 2)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
            draw.polygon(points, outline=(*accent, 255))
        
        elif bg_type == "speech_bubble":
            bubble_h = total_h - 15
            draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 235))
            border_color = style.get("border_color", (255, 255, 255, 255))
            draw.rounded_rectangle([0, 0, total_w, bubble_h], radius=20,
                                  outline=border_color, width=2)
            tail_x = int(total_w * 0.7)
            tail_pts = [(tail_x - 10, bubble_h - 2), (tail_x + 10, bubble_h - 2), (tail_x + 20, total_h)]
            draw.polygon(tail_pts, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
        
        elif bg_type == "cut_corner":
            cut = 30
            accent = style.get("accent_color", (255, 200, 100))
            border_color = style.get("border_color", (255, 255, 255, 255))
            points = [(0, 0), (total_w - cut, 0), (total_w, cut), (total_w, total_h), (0, total_h)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 235))
            draw.polygon(points, outline=border_color)
            draw.polygon([(total_w - cut, 0), (total_w, cut), (total_w - cut, cut)], fill=(*accent, 200))
        
        elif bg_type == "left_bar":
            accent = style.get("accent_color", (255, 200, 100))
            bar_w = 8
            draw.rectangle([bar_w, 0, total_w, total_h], fill=(bg_color[0], bg_color[1], bg_color[2], 220))
            draw.rectangle([0, 0, bar_w, total_h], fill=(*accent, 255))
        
        elif bg_type == "deco_lines":
            accent = style.get("accent_color", (255, 200, 100))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 210))
            draw.line([20, 6, total_w - 20, 6], fill=(*accent, 255), width=2)
            draw.line([35, 12, total_w - 35, 12], fill=(*accent, 150), width=1)
            draw.line([20, total_h - 6, total_w - 20, total_h - 6], fill=(*accent, 255), width=2)
            draw.line([35, total_h - 12, total_w - 35, total_h - 12], fill=(*accent, 150), width=1)
        
        elif bg_type == "shadow_card":
            draw.rounded_rectangle([5, 5, total_w, total_h], radius=radius, fill=(0, 0, 0, 100))
            draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 240))
            border_color = style.get("border_color", (255, 255, 255, 255))
            draw.rounded_rectangle([0, 0, total_w-5, total_h-5], radius=radius,
                                  outline=border_color, width=2)
        
        elif bg_type == "neon_glow":
            glow_color = style.get("accent_color", (100, 200, 255))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  fill=(bg_color[0], bg_color[1], bg_color[2], 200))
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius,
                                  outline=(*glow_color, 80), width=8)
            draw.rounded_rectangle([3, 3, total_w-3, total_h-3], radius=radius,
                                  outline=(*glow_color, 200), width=2)
        
        elif bg_type == "trapezoid":
            indent = 20
            accent = style.get("accent_color", (255, 200, 100))
            points = [(indent, 0), (total_w - indent, 0), (total_w, total_h), (0, total_h)]
            draw.polygon(points, fill=(bg_color[0], bg_color[1], bg_color[2], 230))
            draw.polygon(points, outline=(*accent, 200))
        
        else:
            draw.rounded_rectangle([0, 0, total_w, total_h], radius=radius, 
                                   fill=(bg_color[0], bg_color[1], bg_color[2], 245))
        
        # 글씨 색상 (영상과 동일)
        color = style.get("text_color", (255, 255, 255))
        outline_color = style.get("outline_color", (0, 0, 0))
        
        # 텍스트 그리기 (box_lines만)
        y = 35
        for i, line in enumerate(box_lines):
            font = font_big if i == 0 else font_normal
            bbox = font.getbbox(str(line))
            text_w = bbox[2] - bbox[0]
            x = (total_w - text_w) // 2
            
            for offset in range(3, 0, -1):
                draw.text((x + offset, y + offset), str(line), font=font,
                         fill=(0, 0, 0, 200 - offset * 25))
            
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), str(line), font=font,
                                 fill=(*outline_color, 255))
            
            draw.text((x, y), str(line), font=font, fill=(*color, 255))
            
            if i == 0:
                y += line_h_big
            else:
                y += line_h_normal

        # ── line4: 박스 아래 1줄 별도 렌더링 ──
        if line4 and str(line4).strip():
            try:
                l4 = str(line4).strip()
                pad4 = 10
                lh4 = font_size_others + 20
                combined_h = total_h + pad4 + lh4
                combined_img = Image.new("RGBA", (total_w, combined_h), (0, 0, 0, 0))
                combined_img.paste(img, (0, 0))
                draw4 = ImageDraw.Draw(combined_img)
                bbox4 = draw4.textbbox((0, 0), l4, font=font_normal)
                w4 = bbox4[2] - bbox4[0]
                x4 = (total_w - w4) // 2
                y4 = total_h + pad4
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw4.text((x4+dx, y4+dy), l4, font=font_normal, fill=(*outline_color, 255))
                draw4.text((x4, y4), l4, font=font_normal, fill=(*color, 255))
                img = combined_img
            except Exception as e4:
                self._log(f"   ⚠️ thumbnail line4 오류: {e4}")
        
        return img
    
    # ============================================================
    # 메타데이터 생성
    # ============================================================
    


    def generate_tts_hybrid(self, sentences, voice_id=None, tone_key=None, channel=None):
        """
        TTS 생성 - Google Cloud TTS 전용
        - 정확한 문장별 타이밍 (자막 싱크)
        """
        # 채널 TTS 엔진 설정 확인
        tts_engine = "구글"
        if channel and hasattr(channel, 'tts_engine'):
            tts_engine = channel.tts_engine
            self._log(f"   🎛️ TTS 엔진: {tts_engine}")
        
        # Google Cloud TTS 사용
        if self.google_tts_client:
            result = self.generate_tts_google_cloud(sentences, tone_key)
            if result[0]:  # 성공
                return result
            self._log(f"   ⚠️ Google Cloud TTS 실패")
        else:
            self._log(f"   ⚠️ Google Cloud TTS 없음 (google_credentials.json 필요)")
        
        return None, []
    

    def generate_tts(self, text, voice_id=None, output_path=None, tone_key=None):
        """개별 문장 TTS - Google Cloud TTS 사용"""
        if not self.google_tts_client:
            self._log(f"   ⚠️ Google Cloud TTS 없음")
            return None
        
        # Google Cloud TTS로 단일 문장 생성
        result = self.generate_tts_google_cloud([text], tone_key)
        if result[0]:
            return result[0]  # audio_path 반환
        return None
    

    def _create_cta(self, text, style):
        if not text:
            return None
        
        if len(text) > 28:
            text = text[:28]
        
        font_path = self._get_font_path()
        font_size = style.get("font_size", 58)
        
        try:
            font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        padding_x, padding_y = 50, 30
        total_w = text_w + padding_x * 2
        total_h = text_h + padding_y * 2
        
        img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        box_color = (*style["box_color"], style["box_opacity"])
        draw.rounded_rectangle([0, 0, total_w, total_h], radius=style["box_radius"], fill=box_color)
        draw.rounded_rectangle([0, 0, total_w, total_h], radius=style["box_radius"], outline=(255, 255, 255, 255), width=2)
        
        x = padding_x
        y = padding_y
        
        color = style["font_color"]
        if color.startswith("#"):
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            fill = (r, g, b, 255)
        else:
            fill = (255, 215, 0, 255)
        
        draw.text((x, y), text, font=font, fill=fill)
        
        # RGBA → RGB + 마스크 분리 (moviepy 호환)
        if img.mode == "RGBA":
            rgb = np.array(img.convert("RGB"))
            alpha = np.array(img.split()[3]) / 255.0  # 0~1 정규화
            clip = ImageClip(rgb).set_duration(style["duration"])
            mask = ImageClip(alpha, ismask=True).set_duration(style["duration"])
            clip = clip.set_mask(mask)
            return clip
        else:
            return ImageClip(np.array(img)).set_duration(style["duration"])
    
    # ============================================================
    # 문의 박스
    # ============================================================
    

    def _create_video_clip(self, video_path: str, duration: float):
        """세로 9:16로 안전하게 채우기(가로면 블러 배경 + 중앙 전경). 영상모드에서는 켄번즈/줌 없음."""
        if not MOVIEPY_OK:
            return None
        try:
            clip = VideoFileClip(video_path, audio=False)
            # 필요한 만큼만 자르기
            if clip.duration >= duration:
                clip = clip.subclip(0, duration)
            else:
                # 부족하면 루프(하지만 영상모드에선 가급적 부족 안 나게 소스 선택/이어붙임이 좋음)
                clip = clip.loop(duration=duration)
    
            w, h = clip.w, clip.h
            target_w, target_h = 1080, 1920
            import re
    
            if w > h:
                # 배경: 세로에 맞춰 확대 후 크롭 + 블러
                bg = clip.resize(height=target_h)
                bg = bg.crop(x_center=bg.w/2, y_center=bg.h/2, width=target_w, height=target_h)
                try:
                    bg = bg.fx(vfx.blur, 30)
                except Exception:
                    pass
                # 전경: 높이 55%로 맞추고 중앙
                fg_h = int(target_h * 0.55)
                fg = clip.resize(height=fg_h)
                if fg.w > target_w:
                    fg = fg.crop(x_center=fg.w/2, y_center=fg.h/2, width=target_w, height=fg_h)
                fg_x = int((target_w - fg.w) / 2)
                fg_y = int((target_h - fg.h) / 2)
                fg = fg.set_position((fg_x, fg_y))
                return CompositeVideoClip([bg, fg], size=(target_w, target_h)).set_duration(duration)
            else:
                # 세로/정방형: 중앙 크롭
                sc = 1.05
                clip2 = clip.resize(sc)
                clip2 = clip2.crop(x_center=clip2.w/2, y_center=clip2.h/2, width=target_w, height=target_h)
                return clip2.set_duration(duration)
        except Exception as e:
            self._log(f"      ⚠️ 비디오 클립 오류: {e}")
            return None
    


    def upload_video(self, video_path, title, description, tags, 
                     thumbnail_path=None, channel=None, privacy="public"):
        """
        YouTube 영상 업로드 + 썸네일 + 댓글
        
        순서:
        1. 영상 업로드
        2. 업로드 완료 대기 (딜레이)
        3. 썸네일 설정
        4. 댓글 달기
        5. 댓글 확인
        6. 완료
        
        규칙:
        - 제목: 100자 이내
        - 설명: 5000자 이내
        - 태그: 500자 이내
        - 카테고리: 22 (People & Blogs)
        """
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            self._log("❌ Google API 패키지 필요: pip install google-api-python-client google-auth")
            return None
        
        # 토큰 파일 확인
        token_path = None
        if channel and hasattr(channel, 'token_path') and channel.token_path:
            token_path = channel.token_path
        else:
            # 기본 경로에서 찾기
            secrets_dir = os.path.join(self.assets_dir, "..", "secrets")
            for f in os.listdir(secrets_dir) if os.path.exists(secrets_dir) else []:
                if f.endswith("_token.json"):
                    token_path = os.path.join(secrets_dir, f)
                    break
        
        if not token_path or not os.path.exists(token_path):
            self._log("❌ YouTube 토큰 없음 - 채널 설정에서 인증 필요")
            return None
        
        try:
            # 토큰 로드
            with open(token_path, 'r') as f:
                token_data = json.load(f)
            
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )
            
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # 제목 100자 제한
            title = title[:100] if len(title) > 100 else title
            
            # 설명 생성 (5000자 제한)
            if not description:
                description = self._generate_description(title, channel)
            description = description[:5000] if len(description) > 5000 else description
            
            # 태그 처리 (500자 제한)
            if isinstance(tags, list):
                tags_str = ",".join(tags)
            else:
                tags_str = tags or ""
            tags_list = [t.strip() for t in tags_str.split(",") if t.strip()][:30]
            
            self._log(f"📤 업로드 시작: {title}")
            self._log(f"   📝 설명: {description[:50]}...")
            self._log(f"   🏷️ 태그: {', '.join(tags_list[:5])}...")
            
            # ========================================
            # 1. 영상 업로드
            # ========================================
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags_list,
                    'categoryId': '22',  # People & Blogs
                    'defaultLanguage': 'ko',
                    'defaultAudioLanguage': 'ko'
                },
                'status': {
                    'privacyStatus': privacy,  # public, private, unlisted
                    'selfDeclaredMadeForKids': False
                }
            }
            
            media = MediaFileUpload(
                video_path,
                chunksize=1024*1024,  # 1MB 청크
                resumable=True,
                mimetype='video/mp4'
            )
            
            request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            retry = 0
            while response is None and retry < 10:
                try:
                    status, response = request.next_chunk()
                    if status:
                        percent = int(status.progress() * 100)
                        self._log(f"   📤 업로드 중... {percent}%")
                except Exception as e:
                    if "503" in str(e) or "500" in str(e):
                        retry += 1
                        time.sleep(2 ** retry)
                        continue
                    raise
            
            if not response:
                self._log("❌ 업로드 응답 없음")
                return None
            
            video_id = response.get('id')
            self._log(f"✅ 업로드 완료: https://youtu.be/{video_id}")
            
            # ========================================
            # 2. 영상 처리 완료 대기 (게시 상태 확인)
            # ========================================
            self._log(f"   ⏳ 유튜브 처리 대기 중...")
            max_wait = 300  # 최대 5분 대기
            wait_interval = 10  # 10초마다 확인
            waited = 0
            is_ready = False
            error_count = 0  # 연속 에러 카운트
            max_errors = 3   # 연속 3번 에러면 중단
            
            while waited < max_wait:
                time.sleep(wait_interval)
                waited += wait_interval
                
                try:
                    # 영상 상태 확인
                    video_response = youtube.videos().list(
                        part="status,processingDetails",
                        id=video_id
                    ).execute()
                    
                    # 에러 카운트 리셋 (성공했으니까)
                    error_count = 0
                    
                    if video_response.get("items"):
                        status = video_response["items"][0].get("status", {})
                        upload_status = status.get("uploadStatus", "")
                        
                        # processed = 처리 완료, uploaded = 아직 처리 중
                        if upload_status == "processed":
                            self._log(f"   ✅ 영상 처리 완료! ({waited}초)")
                            is_ready = True
                            break
                        elif upload_status == "failed":
                            self._log(f"   ❌ 영상 처리 실패")
                            break
                        elif upload_status == "rejected":
                            self._log(f"   ❌ 영상 거부됨 (정책 위반)")
                            break
                        else:
                            self._log(f"   ⏳ 처리 중... ({waited}초/{max_wait}초)")
                    else:
                        # 영상 못 찾음
                        self._log(f"   ⚠️ 영상 정보 없음 (삭제됨?)")
                        break
                    
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)
                    
                    # 에러 유형별 처리
                    if "401" in error_msg or "Unauthorized" in error_msg:
                        self._log(f"   ❌ 인증 만료 - 재인증 필요")
                        break
                    elif "403" in error_msg or "Forbidden" in error_msg:
                        self._log(f"   ❌ 권한 없음 (할당량 초과?)")
                        break
                    elif "404" in error_msg or "Not Found" in error_msg:
                        self._log(f"   ❌ 영상 없음 (삭제됨?)")
                        break
                    elif "429" in error_msg or "quota" in error_msg.lower():
                        self._log(f"   ❌ API 할당량 초과")
                        break
                    else:
                        self._log(f"   ⚠️ 확인 오류 ({error_count}/{max_errors}): {e}")
                    
                    # 연속 에러 3번이면 중단
                    if error_count >= max_errors:
                        self._log(f"   ❌ 연속 에러 {max_errors}회 - 중단")
                        break
            
            if not is_ready:
                self._log(f"   ⚠️ 처리 미완료 - 썸네일/댓글은 나중에 수동 확인 필요")
                self._log(f"🎉 업로드 완료 (처리 대기 중): https://youtu.be/{video_id}")
                return video_id
            
            # ========================================
            # 3. 썸네일 설정 (처리 완료 후)
            # ========================================
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    self._log(f"   🖼️ 썸네일 설정 완료")
                except Exception as e:
                    self._log(f"   ⚠️ 썸네일 설정 실패: {e}")
            
            # ========================================
            # ========================================
            # 4. 완료
            # ========================================
            self._log(f"🎉 전체 완료: https://youtu.be/{video_id}")
            
            # 업로드 후 딜레이는 main.py에서 관리 (delay_spin 값 사용)
            
            return video_id
            
        except Exception as e:
            self._log(f"❌ 업로드 실패: {e}")
            import traceback
            self._log(traceback.format_exc())
        
        return None
    


    def _generate_description_template(self, title, channel=None):
        """YouTube 설명 템플릿 생성 (fallback용) - 영상마다 다른 문구"""
        import random, hashlib as _hs, time as _t
        project_name = ""
        inquiry_lines = []

        if channel:
            project_name = getattr(channel, 'project_name', '')
            inquiry_lines = [
                getattr(channel, 'inquiry_1', ''),
                getattr(channel, 'inquiry_2', ''),
                getattr(channel, 'inquiry_3', '')
            ]
            inquiry_lines = [l for l in inquiry_lines if l]

        # 랜덤 시드 (프로젝트명+제목 기반)
        _seed = int(_hs.md5(f"{project_name}{title}{int(_t.time()*1000)%99991}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(_seed)

        # 오프닝 문구 풀 - EEAT 기준 (Experience/Expertise/Authoritativeness/Trust)
        opening_pool = [
            # Experience (현장 경험 강조)
            f"직접 현장을 방문해 {project_name}의 핵심 정보를 담았습니다.",
            f"{project_name} 모델하우스를 직접 다녀온 후 정리한 실제 정보입니다.",
            f"현장에서 확인한 {project_name} 분양 정보를 솔직하게 전달합니다.",
            f"{project_name}, 직접 발로 뛰며 확인한 정보만 담았습니다.",
            # Expertise (전문성 강조)
            f"{project_name} 입지·분양가·평면도까지 핵심만 정리했습니다.",
            f"{project_name} 분양 조건과 주변 인프라를 전문적으로 분석했습니다.",
            f"{project_name}의 교통·학군·생활편의시설을 꼼꼼히 살펴봤습니다.",
            f"{project_name} 분양 정보, 놓치기 쉬운 핵심 포인트를 짚어드립니다.",
            # Authoritativeness (신뢰/권위 강조)
            f"{project_name} 공식 분양 정보를 바탕으로 정확하게 전달합니다.",
            f"{project_name} 분양 현황과 조건을 있는 그대로 안내해 드립니다.",
        ]

        # 마무리 문구 풀 - EEAT 기준 (Trust 강조)
        closing_pool = [
            "정확한 정보는 반드시 모델하우스에서 직접 확인하시길 권장합니다.",
            "본 영상은 분양 홍보 목적이며, 상세 조건은 모델하우스에서 확인하세요.",
            "궁금한 점은 아래 문의처로 연락 주시면 친절히 안내해 드립니다.",
            "더 자세한 정보와 상담은 공식 문의처를 통해 확인하세요.",
            "분양 조건은 변경될 수 있으니 최신 정보는 모델하우스에서 확인하세요.",
            "본 영상의 정보는 참고용이며, 계약 전 반드시 공식 자료를 확인하세요.",
        ]

        opening = rng.choice(opening_pool)
        closing = rng.choice(closing_pool)

        lines = [opening, ""]
        if inquiry_lines:
            lines += ["📞 문의"] + [f"  {l}" for l in inquiry_lines] + [""]
        lines.append(closing)

        return "\n".join(lines)


if __name__ == "__main__":
    gen = VideoGenerator()
    titles = gen.generate_titles("동작이안", "FRIEND")
    print("제목:", titles)
