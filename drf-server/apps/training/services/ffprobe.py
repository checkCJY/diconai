"""
apps/training/services/ffprobe.py — VR 영상 재생 시간 추출.

[원칙]
ffprobe 미설치/타임아웃/파싱 실패 시 None을 반환한다. 업로드 자체를 막지 않는다.
None은 DB에 그대로 저장되어 화면에서는 "—" 표기되며, 후속 수동 보정 여지를 남긴다.

[보안]
- subprocess는 list 인자 형태로만 호출 (shell=False) → shell injection 차단.
- 외부 경로는 절대 경로만 받고, ffprobe 자체 검색은 shutil.which로 가드.
"""

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

FFPROBE_TIMEOUT_SEC = 15


def probe_duration_seconds(path: str) -> int | None:
    """영상 파일의 재생 시간을 초 단위 정수로 추출.

    Args:
        path: MEDIA_ROOT 하위 영상의 절대 경로. service 레이어가 파일 저장
            직후 전달하므로 호출 시점에 파일이 존재함을 전제.

    Returns:
        영상 길이(초, 반올림된 int). 다음 경우 모두 None:
        - ffprobe 바이너리 미설치 (`shutil.which` 가드)
        - 15초 타임아웃 초과
        - subprocess 비정상 종료 (`CalledProcessError`)
        - 출력 파싱 실패 (숫자가 아닌 문자열)

    [업로드 차단 안 함]
    None 반환 시 호출부는 `duration_seconds=None`으로 DB 저장하고 응답에는
    클라이언트가 `<video>.loadedmetadata`로 보강해 표시한다. 영상 자체는
    정상 업로드되며, 후속 수동 보정 여지를 남긴다.

    [보안]
    `subprocess.run`은 list 인자 형태 + `shell=False` 기본값으로 호출되어
    경로에 메타문자가 있어도 shell injection으로 이어지지 않는다.
    """
    if not shutil.which("ffprobe"):
        logger.warning("ffprobe 미설치 — duration 추출 생략")
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SEC,
            check=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe 타임아웃: %s", path)
        return None
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "ffprobe 실패 rc=%s stderr=%s", exc.returncode, (exc.stderr or "")[:300]
        )
        return None
    raw = (proc.stdout or "").strip()
    try:
        return int(round(float(raw)))
    except ValueError:
        logger.warning("ffprobe 출력 파싱 실패: %r", raw)
        return None
