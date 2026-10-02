/**
 * 분양쇼츠 Express API - Railway 배포용
 * 사진 + 대본 + 음성(mp3) → ffmpeg로 MP4 생성
 * 대본/TTS는 브라우저에서 처리 후 넘겨줌
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');
const express = require('express');
const cors = require('cors');
const multer = require('multer');

const app = express();
app.use(cors());

const WORK_DIR = '/tmp/shorts_work';
fs.mkdirSync(WORK_DIR, { recursive: true });

// 명령 실행 (실패해도 reject 하지 않고 결과 반환)
function run(cmd, args) {
  return new Promise((resolve) => {
    execFile(cmd, args, { maxBuffer: 64 * 1024 * 1024 }, (err, stdout, stderr) => {
      resolve({ code: err ? (typeof err.code === 'number' ? err.code : 1) : 0, stdout: stdout || '', stderr: stderr || '' });
    });
  });
}

async function findFont() {
  const candidates = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKkr-Bold.otf',
  ];
  for (const f of candidates) {
    if (fs.existsSync(f)) return f;
  }
  // 검색
  const r = await run('find', ['/usr/share/fonts', '-name', '*Noto*Bold*', '-type', 'f']);
  const line = r.stdout.split('\n').map((l) => l.trim()).find(Boolean);
  return line || null;
}

// 작업 폴더 생성 + 5분 뒤 삭제 예약
function newJob(req, res, next) {
  req.jobId = crypto.randomUUID().slice(0, 8);
  req.jobDir = path.join(WORK_DIR, req.jobId);
  fs.mkdirSync(req.jobDir, { recursive: true });
  res.on('close', () => {
    setTimeout(() => fs.rmSync(req.jobDir, { recursive: true, force: true }), 300 * 1000).unref();
  });
  next();
}

const upload = multer({
  storage: multer.diskStorage({
    destination: (req, file, cb) => {
      const dir = path.join(req.jobDir, 'uploads');
      fs.mkdirSync(dir, { recursive: true });
      cb(null, dir);
    },
    filename: (req, file, cb) => cb(null, crypto.randomUUID()),
  }),
}).any();

const formInt = (v, d) => {
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? d : n;
};
// 작은따옴표는 ffmpeg 필터에서 이스케이프가 안 되므로 ’ 로 바꿔서 넣음
const escapeDrawtext = (s) =>
  s.replace(/'/g, '’').replace(/\\/g, '\\\\').replace(/:/g, '\\:').replace(/,/g, '\\,').replace(/%/g, '\\%');
const tail = (s, n) => s.slice(-n);

app.get('/health', async (req, res) => {
  const r = await run('ffmpeg', ['-version']);
  const ffmpegOk = r.stdout.includes('ffmpeg version');
  const font = await findFont();
  res.json({ status: 'ok', ffmpeg: ffmpegOk, font });
});

app.post('/render', newJob, upload, async (req, res) => {
  const { jobId, jobDir } = req;
  try {
    const body = req.body || {};
    const files = req.files || [];
    const projectName = (body.project_name || '분양').trim();
    const script = (body.script || '').trim();
    const inqTitle = body.inq_title || '분양상담센터';
    const inqTime = body.inq_time || '평일 9시~6시';
    const inqPhone = body.inq_phone || '1844-1148';
    const inqPos = formInt(body.inq_position, 5);
    const subSize = formInt(body.sub_size, 52);
    const inqSize1 = formInt(body.inq_size1, 90);
    const inqSize2 = formInt(body.inq_size2, 70);

    // 음성 저장
    const audioFile = files.find((f) => f.fieldname === 'audio');
    if (!audioFile) return res.status(400).json({ success: false, error: '음성 파일 없음' });
    const audioPath = path.join(jobDir, 'audio.mp3');
    fs.renameSync(audioFile.path, audioPath);

    // 사진 저장
    const photos = files.filter((f) => f.fieldname === 'photos[]');
    if (!photos.length) return res.status(400).json({ success: false, error: '사진 없음' });
    const photoDir = path.join(jobDir, 'photos');
    fs.mkdirSync(photoDir, { recursive: true });
    const photoPaths = photos.slice(0, 20).map((p, i) => {
      let ext = path.extname(p.originalname).toLowerCase() || '.jpg';
      if (!['.jpg', '.jpeg', '.png', '.webp'].includes(ext)) ext = '.jpg';
      const dest = path.join(photoDir, `p${String(i).padStart(3, '0')}${ext}`);
      fs.renameSync(p.path, dest);
      return dest;
    });

    // 음성 길이
    const probe = await run('ffprobe', ['-v', 'quiet', '-print_format', 'json', '-show_format', audioPath]);
    let duration = 25.0;
    try {
      const d = parseFloat(JSON.parse(probe.stdout).format.duration);
      if (!Number.isNaN(d)) duration = d;
    } catch (e) {}

    console.log(`[INFO] job=${jobId} 사진=${photoPaths.length} 음성=${duration.toFixed(1)}s`);

    // 자막 문장
    const sentences = script ? script.split('\n').map((s) => s.trim()).filter(Boolean) : [''];
    const secPerSent = duration / Math.max(sentences.length, 1);
    const secPerPhoto = duration / Math.max(photoPaths.length, 1);

    // 각 사진 → 클립
    const clipsDir = path.join(jobDir, 'clips');
    fs.mkdirSync(clipsDir, { recursive: true });
    const clipPaths = [];

    for (const [i, pp] of photoPaths.entries()) {
      const cp = path.join(clipsDir, `c${String(i).padStart(3, '0')}.mp4`);
      const r = await run('ffmpeg', [
        '-y', '-loop', '1', '-i', pp,
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
        '-t', String(secPerPhoto), '-r', '25',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
        '-pix_fmt', 'yuv420p', '-tune', 'stillimage', cp,
      ]);
      if (r.code === 0) clipPaths.push(cp);
      else console.log(`[WARN] 클립${i} 실패: ${tail(r.stderr, 100)}`);
    }

    if (!clipPaths.length) return res.status(500).json({ success: false, error: '클립 생성 실패' });

    // 클립 합치기
    const concatTxt = path.join(jobDir, 'list.txt');
    fs.writeFileSync(concatTxt, clipPaths.map((cp) => `file '${cp}'\n`).join(''));
    const concatMp4 = path.join(jobDir, 'concat.mp4');
    await run('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', concatTxt, '-c', 'copy', concatMp4]);

    // 자막+문의박스+음성 합성
    const font = await findFont();
    const vfParts = [];

    if (font && sentences.length) {
      sentences.forEach((s, i) => {
        if (!s) return;
        const t0 = i * secPerSent;
        const t1 = t0 + secPerSent;
        vfParts.push(
          `drawtext=fontfile='${font}':text='${escapeDrawtext(s)}':fontsize=${subSize}` +
          `:fontcolor=white:borderw=4:bordercolor=black` +
          `:x=(w-text_w)/2:y=h*0.69:enable='between(t,${t0.toFixed(2)},${t1.toFixed(2)})'`
        );
      });
    }

    if (font) {
      const p = inqPos / 100;
      for (const [text, sz, offset, color] of [
        [inqTitle, inqSize1, 10, 'white'],
        [inqTime, inqSize2, inqSize1 + 25, '#64E8F0'],
        [inqPhone, inqSize2, inqSize1 + inqSize2 + 45, '#64E8F0'],
      ]) {
        vfParts.push(
          `drawtext=fontfile='${font}':text='${escapeDrawtext(text)}':fontsize=${sz}` +
          `:fontcolor=${color}:borderw=5:bordercolor=black` +
          `:x=(w-text_w)/2:y=h*${p.toFixed(3)}+${offset}`
        );
      }
    }

    const vf = vfParts.length ? vfParts.join(',') : 'null';
    const output = path.join(jobDir, `${projectName}_쇼츠.mp4`);
    const encodeArgs = [
      '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
      '-c:a', 'aac', '-b:a', '128k',
      '-shortest', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
      output,
    ];

    const r = await run('ffmpeg', ['-y', '-i', concatMp4, '-i', audioPath, '-vf', vf, ...encodeArgs]);
    if (r.code !== 0) {
      console.log(`[WARN] vf 실패, 단순 합성 재시도: ${tail(r.stderr, 300)}`);
      const r2 = await run('ffmpeg', ['-y', '-i', concatMp4, '-i', audioPath, ...encodeArgs]);
      if (r2.code !== 0) return res.status(500).json({ success: false, error: tail(r2.stderr, 300) });
    }

    const size = fs.existsSync(output) ? fs.statSync(output).size : 0;
    console.log(`[INFO] 완료 ${(size / 1024 / 1024).toFixed(1)}MB`);

    res.download(output, `${projectName}_쇼츠.mp4`, { headers: { 'Content-Type': 'video/mp4' } });
  } catch (e) {
    console.log(`[ERROR] ${e.stack}`);
    res.status(500).json({ success: false, error: String(e.message || e) });
  }
});

app.post('/convert', newJob, upload, async (req, res) => {
  // WebM + MP3 → MP4 변환
  const { jobId, jobDir } = req;
  try {
    const body = req.body || {};
    const files = req.files || [];
    const projectName = (body.project_name || '분양').trim();
    const videoFile = files.find((f) => f.fieldname === 'video');
    const audioFile = files.find((f) => f.fieldname === 'audio');
    if (!videoFile) return res.status(400).json({ success: false, error: '영상 파일 없음' });
    if (!audioFile) return res.status(400).json({ success: false, error: '음성 파일 없음' });

    const webmPath = path.join(jobDir, 'input.webm');
    const audioPath = path.join(jobDir, 'audio.mp3');
    const outputPath = path.join(jobDir, `${projectName}_쇼츠.mp4`);
    fs.renameSync(videoFile.path, webmPath);
    fs.renameSync(audioFile.path, audioPath);

    console.log(`[INFO] convert job=${jobId} webm=${(fs.statSync(webmPath).size / 1024).toFixed(0)}KB`);

    const r = await run('ffmpeg', [
      '-y', '-i', webmPath, '-i', audioPath,
      '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
      '-c:a', 'aac', '-b:a', '128k',
      '-shortest', '-pix_fmt', 'yuv420p',
      '-movflags', '+faststart', outputPath,
    ]);
    if (r.code !== 0) {
      console.log(`[WARN] 오디오 합성 실패, 비디오만 변환: ${tail(r.stderr, 200)}`);
      const r2 = await run('ffmpeg', [
        '-y', '-i', webmPath,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outputPath,
      ]);
      if (r2.code !== 0) return res.status(500).json({ success: false, error: tail(r2.stderr, 200) });
    }

    const outSize = fs.existsSync(outputPath) ? fs.statSync(outputPath).size : 0;
    console.log(`[INFO] 완료 ${(outSize / 1024 / 1024).toFixed(1)}MB`);
    res.download(outputPath, `${projectName}_쇼츠.mp4`, { headers: { 'Content-Type': 'video/mp4' } });
  } catch (e) {
    console.log(`[ERROR] ${e.stack}`);
    res.status(500).json({ success: false, error: String(e.message || e) });
  }
});

const port = parseInt(process.env.PORT || '5000', 10);
const server = app.listen(port, '0.0.0.0', () => console.log(`[INFO] 서버 시작 :${port}`));
server.requestTimeout = 300 * 1000;
