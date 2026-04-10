"""
분양쇼츠 Flask API - Railway 배포용
사진 + 대본 + 음성(mp3) → ffmpeg로 MP4 생성
대본/TTS는 브라우저에서 처리 후 넘겨줌
"""
import os, sys, json, uuid, shutil, subprocess, traceback
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
WORK_DIR = '/tmp/shorts_work'
os.makedirs(WORK_DIR, exist_ok=True)

def find_font():
    candidates = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJKkr-Bold.otf',
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    # 검색
    try:
        r = subprocess.run(['find', '/usr/share/fonts', '-name', '*Noto*Bold*', '-type', 'f'],
                           capture_output=True, text=True)
        lines = r.stdout.strip().split('\n')
        for l in lines:
            if l.strip():
                return l.strip()
    except:
        pass
    return None

@app.route('/health', methods=['GET'])
def health():
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        ffmpeg_ok = 'ffmpeg version' in r.stdout
    except:
        ffmpeg_ok = False
    font = find_font()
    return jsonify({'status': 'ok', 'ffmpeg': ffmpeg_ok, 'font': font})

@app.route('/render', methods=['POST'])
def render():
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        project_name = request.form.get('project_name', '분양').strip()
        script       = request.form.get('script', '').strip()
        inq_title    = request.form.get('inq_title', '분양상담센터')
        inq_time     = request.form.get('inq_time', '평일 9시~6시')
        inq_phone    = request.form.get('inq_phone', '1844-1148')
        inq_pos      = int(request.form.get('inq_position', 5))
        sub_size     = int(request.form.get('sub_size', 52))
        inq_size1    = int(request.form.get('inq_size1', 90))
        inq_size2    = int(request.form.get('inq_size2', 70))

        # 음성 저장
        audio_file = request.files.get('audio')
        if not audio_file:
            return jsonify({'success': False, 'error': '음성 파일 없음'}), 400
        audio_path = os.path.join(job_dir, 'audio.mp3')
        audio_file.save(audio_path)

        # 사진 저장
        photos = request.files.getlist('photos[]')
        if not photos:
            return jsonify({'success': False, 'error': '사진 없음'}), 400
        photo_dir = os.path.join(job_dir, 'photos')
        os.makedirs(photo_dir, exist_ok=True)
        photo_paths = []
        for i, p in enumerate(photos[:20]):
            ext = os.path.splitext(p.filename)[1].lower() or '.jpg'
            if ext not in ['.jpg','.jpeg','.png','.webp']: ext = '.jpg'
            path = os.path.join(photo_dir, f'p{i:03d}{ext}')
            p.save(path)
            photo_paths.append(path)

        # 음성 길이
        probe = subprocess.run(['ffprobe','-v','quiet','-print_format','json','-show_format', audio_path],
                               capture_output=True, text=True)
        duration = 25.0
        try:
            duration = float(json.loads(probe.stdout)['format']['duration'])
        except: pass

        print(f"[INFO] job={job_id} 사진={len(photo_paths)} 음성={duration:.1f}s")

        # 자막 문장
        sentences = [s.strip() for s in script.split('\n') if s.strip()] if script else ['']
        sec_per_sent = duration / max(len(sentences), 1)
        sec_per_photo = duration / max(len(photo_paths), 1)

        # 각 사진 → 클립
        clips_dir = os.path.join(job_dir, 'clips')
        os.makedirs(clips_dir, exist_ok=True)
        clip_paths = []

        for i, pp in enumerate(photo_paths):
            cp = os.path.join(clips_dir, f'c{i:03d}.mp4')
            cmd = [
                'ffmpeg', '-y', '-loop', '1', '-i', pp,
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
                '-t', str(sec_per_photo), '-r', '25',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                '-pix_fmt', 'yuv420p', '-tune', 'stillimage', cp
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                clip_paths.append(cp)
            else:
                print(f"[WARN] 클립{i} 실패: {r.stderr[-100:]}")

        if not clip_paths:
            return jsonify({'success': False, 'error': '클립 생성 실패'}), 500

        # 클립 합치기
        concat_txt = os.path.join(job_dir, 'list.txt')
        with open(concat_txt, 'w') as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")
        concat_mp4 = os.path.join(job_dir, 'concat.mp4')
        subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',concat_txt,
                        '-c','copy', concat_mp4], capture_output=True)

        # 자막+문의박스+음성 합성
        font = find_font()
        vf_parts = []

        if font and sentences:
            for i, s in enumerate(sentences):
                if not s: continue
                t0 = i * sec_per_sent
                t1 = t0 + sec_per_sent
                safe = s.replace("'","\\'").replace(':','\\:').replace(',','\\,')
                vf_parts.append(
                    f"drawtext=fontfile='{font}':text='{safe}':fontsize={sub_size}"
                    f":fontcolor=white:borderw=4:bordercolor=black"
                    f":x=(w-text_w)/2:y=h*0.69:enable='between(t,{t0:.2f},{t1:.2f})'"
                )

        if font:
            p = inq_pos / 100
            for text, sz, offset, color in [
                (inq_title, inq_size1, 10, 'white'),
                (inq_time,  inq_size2, inq_size1+25, '#64E8F0'),
                (inq_phone, inq_size2, inq_size1+inq_size2+45, '#64E8F0'),
            ]:
                safe = text.replace("'","\\'").replace(':','\\:').replace(',','\\,')
                vf_parts.append(
                    f"drawtext=fontfile='{font}':text='{safe}':fontsize={sz}"
                    f":fontcolor={color}:borderw=5:bordercolor=black"
                    f":x=(w-text_w)/2:y=h*{p:.3f}+{offset}"
                )

        vf = ','.join(vf_parts) if vf_parts else 'null'
        output = os.path.join(job_dir, f'{project_name}_쇼츠.mp4')

        cmd_final = [
            'ffmpeg', '-y',
            '-i', concat_mp4, '-i', audio_path,
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
            '-c:a', 'aac', '-b:a', '128k',
            '-shortest', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            output
        ]
        r = subprocess.run(cmd_final, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[WARN] vf 실패, 단순 합성 재시도: {r.stderr[-300:]}")
            cmd_plain = [
                'ffmpeg', '-y',
                '-i', concat_mp4, '-i', audio_path,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                '-c:a', 'aac', '-b:a', '128k',
                '-shortest', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                output
            ]
            r2 = subprocess.run(cmd_plain, capture_output=True, text=True)
            if r2.returncode != 0:
                return jsonify({'success': False, 'error': r2.stderr[-300:]}), 500

        size = os.path.getsize(output) if os.path.exists(output) else 0
        print(f"[INFO] 완료 {size/1024/1024:.1f}MB")

        return send_file(output, mimetype='video/mp4', as_attachment=True,
                         download_name=f'{project_name}_쇼츠.mp4')

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        import threading
        def cleanup():
            import time; time.sleep(300)
            shutil.rmtree(job_dir, ignore_errors=True)
        threading.Thread(target=cleanup, daemon=True).start()


@app.route('/convert', methods=['POST'])
def convert():
    """WebM + MP3 → MP4 변환"""
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    try:
        project_name = request.form.get('project_name', '분양').strip()
        video_file = request.files.get('video')
        audio_file = request.files.get('audio')
        if not video_file: return jsonify({'success': False, 'error': '영상 파일 없음'}), 400
        if not audio_file: return jsonify({'success': False, 'error': '음성 파일 없음'}), 400

        webm_path = os.path.join(job_dir, 'input.webm')
        audio_path = os.path.join(job_dir, 'audio.mp3')
        output_path = os.path.join(job_dir, f'{project_name}_쇼츠.mp4')
        video_file.save(webm_path)
        audio_file.save(audio_path)

        print(f"[INFO] convert job={job_id} webm={os.path.getsize(webm_path)/1024:.0f}KB")

        cmd = [
            'ffmpeg', '-y',
            '-i', webm_path, '-i', audio_path,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
            '-c:a', 'aac', '-b:a', '128k',
            '-shortest', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', output_path
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[WARN] 오디오 합성 실패, 비디오만 변환: {r.stderr[-200:]}")
            cmd2 = ['ffmpeg', '-y', '-i', webm_path,
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', output_path]
            r2 = subprocess.run(cmd2, capture_output=True, text=True)
            if r2.returncode != 0:
                return jsonify({'success': False, 'error': r2.stderr[-200:]}), 500

        out_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        print(f"[INFO] 완료 {out_size/1024/1024:.1f}MB")
        return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                        download_name=f'{project_name}_쇼츠.mp4')
    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        import threading
        def cleanup():
            import time; time.sleep(300)
            shutil.rmtree(job_dir, ignore_errors=True)
        threading.Thread(target=cleanup, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
