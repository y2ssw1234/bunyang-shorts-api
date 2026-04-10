"""
분양쇼츠 Flask API - Railway 배포용
- 사진 업로드 + 설정 → MP4 생성 → 다운로드
"""
import os
import sys
import json
import uuid
import shutil
import tempfile
import traceback
from flask import Flask, request, jsonify, send_file
import httpx as _httpx

# openai proxies 오류 패치
try:
    import openai._base_client as _obc
    _orig_init = _obc.SyncAPIClient.__init__
    def _patched_init(self, *args, **kwargs):
        kwargs.pop('proxies', None)
        _orig_init(self, *args, **kwargs)
    _obc.SyncAPIClient.__init__ = _patched_init
except Exception:
    pass
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 임시 작업 폴더
WORK_DIR = '/tmp/shorts_work'
os.makedirs(WORK_DIR, exist_ok=True)

# ── API 키 (환경변수로 관리) ──
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '')
GOOGLE_TTS_KEY = os.environ.get('GOOGLE_TTS_KEY', '')

def get_video_generator():
    """VideoGenerator 인스턴스 생성"""
    sys.path.insert(0, os.path.dirname(__file__))
    from video_generator import VideoGenerator
    config = {
        'openai_api_key': OPENAI_KEY,
        'google_credentials': None,
    }
    return VideoGenerator(config=config)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': '분양쇼츠 API 정상 작동 중'})

@app.route('/generate', methods=['POST'])
def generate():
    """
    영상 생성 API
    Form data:
        - photos[]: 사진 파일들
        - project_name: 단지명
        - seeds: 대사 소재 (줄바꿈으로 구분)
        - inq_title: 문의 타이틀
        - inq_time: 상담 시간
        - inq_phone: 전화번호
        - inq_position: 박스 위치 (0~50)
        - tts_speed: TTS 속도 (1.0~1.6)
        - tts_voice: TTS 목소리
    """
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        # ── 파라미터 수집 ──
        project_name = request.form.get('project_name', '').strip()
        seeds = request.form.get('seeds', '').strip()
        inq_title = request.form.get('inq_title', '분양상담센터')
        inq_time = request.form.get('inq_time', '평일 9시~6시')
        inq_phone = request.form.get('inq_phone', '1844-1148')
        inq_pos = int(request.form.get('inq_position', 5))
        tts_speed = float(request.form.get('tts_speed', 1.2))
        tts_voice = request.form.get('tts_voice', 'ko-KR-Wavenet-B')

        if not project_name:
            return jsonify({'success': False, 'error': '단지명이 없습니다'}), 400

        # ── 사진 저장 ──
        photos = request.files.getlist('photos[]')
        if not photos or len(photos) < 1:
            return jsonify({'success': False, 'error': '사진이 없습니다'}), 400

        photo_dir = os.path.join(job_dir, 'photos')
        os.makedirs(photo_dir, exist_ok=True)
        for i, photo in enumerate(photos):
            ext = os.path.splitext(photo.filename)[1] or '.jpg'
            photo.save(os.path.join(photo_dir, f'photo_{i:03d}{ext}'))

        # ── Channel 객체 생성 ──
        class SimpleChannel:
            pass

        ch = SimpleChannel()
        ch.channel_id = job_id
        ch.project_name = project_name
        ch.name = project_name
        ch.photo_folder = photo_dir
        ch.video_folder = ''
        ch.pdf_folder = ''
        ch.selected_modes = ['photos']
        ch.inquiry_1 = inq_title
        ch.inquiry_2 = inq_time
        ch.inquiry_3 = inq_phone
        ch.inquiry_4 = ''
        ch.inquiry_font_size = 90
        ch.inquiry_size_1 = 90
        ch.inquiry_size_2 = 70
        ch.inquiry_size_3 = 70
        ch.inquiry_size_4 = 70
        ch.inquiry_position = inq_pos
        ch.inquiry_no_bg = False
        ch.inquiry_bold = True
        ch.opening_enabled = False
        ch.opening_line1 = ''
        ch.opening_line2 = ''
        ch.link_url = ''
        ch.tts_engine = '구글'
        ch.tts_speed = tts_speed
        ch.character = 'random'
        ch.voice = tts_voice
        ch.tone = 'FRIEND'
        ch.token_path = None
        ch.thumb_line1 = ''
        ch.thumb_line2 = ''

        # ── 대본 생성 ──
        vg = get_video_generator()

        # 대사 소재로 제목 생성
        seed_block = f"\n【대사 소재】\n{seeds}" if seeds else ""
        prompt = f"""너는 유튜브 쇼츠 분양 영상 전문 작가다.
【단지명】 {project_name}{seed_block}
유튜브 쇼츠 제목 1개만 생성해라. 30자 이내, 번호 없이."""

        import openai, httpx
        client = openai.OpenAI(api_key=OPENAI_KEY, http_client=httpx.Client())
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=100,
            temperature=0.9
        )
        title = resp.choices[0].message.content.strip()

        ch.titles = [title]
        ch.current_title_index = 0

        # 대사 소재 파일 저장
        if seeds:
            seed_path = os.path.join(
                os.path.dirname(__file__), 'channels',
                f'{job_id}_script_seeds.txt'
            )
            os.makedirs(os.path.dirname(seed_path), exist_ok=True)
            with open(seed_path, 'w', encoding='utf-8') as f:
                for line in seeds.splitlines():
                    if line.strip():
                        f.write(f'[대사] {line.strip()}\n')

        # ── 영상 생성 ──
        vg._current_mode = 'photos'
        output_path = vg.create_video(ch, 0, 'photos', upload=False)

        if not output_path or not os.path.exists(output_path):
            return jsonify({'success': False, 'error': '영상 생성 실패'}), 500

        # 결과 파일 복사
        result_path = os.path.join(job_dir, f'{project_name}_쇼츠.mp4')
        shutil.copy2(output_path, result_path)

        return send_file(
            result_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'{project_name}_쇼츠.mp4'
        )

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR] {e}\n{tb}")
        return jsonify({'success': False, 'error': str(e), 'traceback': tb}), 500

    finally:
        # 임시 파일 정리 (5분 후)
        import threading
        def cleanup():
            import time
            time.sleep(300)
            shutil.rmtree(job_dir, ignore_errors=True)
        threading.Thread(target=cleanup, daemon=True).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
