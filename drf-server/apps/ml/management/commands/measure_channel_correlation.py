# apps/ml/management/commands/measure_channel_correlation.py
"""
16 채널 watt 시계열 간 Pearson 상관계수 + DTW 거리 측정 (1차 PoC).

[배경] 강사 multivariate IF 제안 검증 — Panel-multivariate IF 적합성은
"채널 간 상관이 강한가" 가 핵심. 운영 데이터 D+30 누적 전 단계로 현재
1주치 dummy 데이터에서 측정해 1차 상관 패턴 확인 → D+30 sprint 의
재측정 비교 기준선 (baseline) 확보가 목적.

[측정 단위] 단일 PowerDevice (기본 1번 = `63200c3afd12`) 의 16채널 watt.
다른 디바이스 비교는 본 PoC 범위 외 (D+90+ 디바이스 클러스터링 단계).

[출력]
1. <out-dir>/pearson_16x16.csv — 전체 데이터 Pearson 상관계수
2. <out-dir>/dtw_16x16.csv — 다운샘플 DTW 거리 (정규화)
3. <out-dir>/pearson_heatmap.png, dtw_heatmap.png — 시각화
4. stdout — 카테고리별 평균 + top-k 상관 채널쌍

사용 예:
    python manage.py measure_channel_correlation \\
        --since 2026-05-22 --until 2026-05-28 \\
        --dtw-samples 1000 --out-dir /tmp/correlation_poc
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

# matplotlib MPLCONFIGDIR — 컨테이너 root home 쓰기 제한 회피.
# matplotlib import 전에 env 설정해야 효과 있어 아래 import 들은 E402 회피.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from django.core.management.base import BaseCommand, CommandError  # noqa: E402
from django.utils.dateparse import parse_datetime  # noqa: E402

from apps.facilities.models import PowerDevice  # noqa: E402
from apps.monitoring.models import PowerData  # noqa: E402


# fastapi-server/dummies/power_dummy.py 와 동기 — 데이터 생성 카테고리 기준.
# (anomaly_inference 의 _INFERENCE_ENABLED_CHANNELS 4채널 분류와는 별개)
MOTOR_CHANNELS = {1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14}
LIGHTING_CHANNELS = {15}
PANEL_CHANNELS = {9, 10, 11, 16}


def _category(ch: int) -> str:
    """채널 → 부하 카테고리. 더미 시뮬레이터 분류와 동기."""
    if ch in MOTOR_CHANNELS:
        return "motor"
    if ch in LIGHTING_CHANNELS:
        return "lighting"
    if ch in PANEL_CHANNELS:
        return "panel"
    return "unknown"


def _parse_dt(s: str) -> datetime:
    dt = parse_datetime(s)
    if dt is None:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_wide_dataframe(
    device_id: int, since: datetime, until: datetime
) -> pd.DataFrame:
    """16채널 watt 시계열을 wide-format (timestamp × ch1..ch16) DataFrame 으로 변환.

    long-format PowerData → pivot 으로 wide 변환. 결측 timestamp 는 forward fill
    (1Hz dummy 기준 한 두 틱 누락 시 보간) 후 NaN 잔존 row 제거.
    """
    qs = PowerData.objects.filter(
        power_device_id=device_id,
        data_type="watt",
        measured_at__gte=since,
        measured_at__lt=until,
    ).values("measured_at", "channel", "value")

    df = pd.DataFrame.from_records(qs)
    if df.empty:
        raise CommandError("PowerData 0 rows — since/until 범위 또는 device-id 확인")

    wide = df.pivot_table(
        index="measured_at", columns="channel", values="value", aggfunc="mean"
    )
    wide.columns = [f"ch{c}" for c in wide.columns]
    wide = wide.sort_index().ffill().dropna()
    return wide


def _dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """numpy 기반 DTW 거리 (Sakoe-Chiba band 미적용 단순 구현).

    PoC 용 — N≤1000 가정 (O(N²) 메모리·시간). 다운샘플 후 호출 전제.
    Z-score 정규화 입력 → 진폭 차이 무관, 시계열 모양만 비교.
    """
    n, m = len(a), len(b)
    inf = float("inf")
    cost = np.full((n + 1, m + 1), inf)
    cost[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = abs(a[i - 1] - b[j - 1])
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    return float(cost[n, m] / (n + m))  # 정규화 — 길이 의존 제거


def _downsample(series: np.ndarray, target: int) -> np.ndarray:
    """평균 다운샘플 — N개 시계열을 target 길이로 축소."""
    n = len(series)
    if n <= target:
        return series
    step = n // target
    truncated = series[: step * target]
    return truncated.reshape(target, step).mean(axis=1)


def _zscore(arr: np.ndarray) -> np.ndarray:
    mean = arr.mean()
    std = arr.std()
    if std < 1e-9:
        return arr - mean
    return (arr - mean) / std


def _save_heatmap(
    matrix: np.ndarray, labels: list[str], title: str, path: Path
) -> None:
    """16×16 매트릭스 heatmap PNG 저장."""
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_title(title)
    plt.colorbar(im, ax=ax)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=6)
    plt.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _category_summary(matrix: pd.DataFrame, channels: list[int]) -> dict[str, float]:
    """카테고리 간(within / between) 평균 매트릭스 값 — 자기 자신 제외."""
    pairs: dict[str, list[float]] = {}
    for i, ci in enumerate(channels):
        for j, cj in enumerate(channels):
            if i >= j:
                continue
            cat_i, cat_j = _category(ci), _category(cj)
            key = "-".join(sorted([cat_i, cat_j]))
            pairs.setdefault(key, []).append(matrix.iloc[i, j])
    return {k: float(np.mean(v)) for k, v in pairs.items()}


class Command(BaseCommand):
    help = "16 channel watt 시계열 상관성(Pearson + DTW) 측정 PoC"

    def add_arguments(self, parser):
        parser.add_argument("--device-id", type=int, default=1)
        parser.add_argument("--since", required=True, help="YYYY-MM-DD or ISO 8601")
        parser.add_argument("--until", required=True, help="YYYY-MM-DD or ISO 8601")
        parser.add_argument(
            "--dtw-samples",
            type=int,
            default=1000,
            help="DTW 입력 다운샘플 길이 (O(N²) 메모리 고려)",
        )
        parser.add_argument(
            "--out-dir",
            default="/tmp/correlation_poc",
            help="결과 CSV / PNG 저장 디렉토리",
        )

    def handle(self, *args, **opts):
        device_id = opts["device_id"]
        since = _parse_dt(opts["since"])
        until = _parse_dt(opts["until"])
        out_dir = Path(opts["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        # 디바이스 존재 검증.
        try:
            device = PowerDevice.objects.get(pk=device_id)
        except PowerDevice.DoesNotExist as exc:
            raise CommandError(f"PowerDevice pk={device_id} 없음") from exc

        self.stdout.write(
            f"[1/4] PowerData 추출 — device={device.device_id} "
            f"since={since.isoformat()} until={until.isoformat()}"
        )
        wide = _fetch_wide_dataframe(device_id, since, until)
        self.stdout.write(
            f"      wide shape={wide.shape} (rows × channels), "
            f"채널={list(wide.columns)}"
        )

        # ----- Pearson 16×16 (전체 데이터) -----
        self.stdout.write("[2/4] Pearson 상관계수 측정 (전체 데이터)")
        pearson = wide.corr(method="pearson")
        pearson.to_csv(out_dir / "pearson_16x16.csv")

        # ----- DTW 16×16 (다운샘플, Z-score 정규화) -----
        target = opts["dtw_samples"]
        self.stdout.write(f"[3/4] DTW 거리 측정 (다운샘플 N={target}, Z-score 정규화)")
        channels = [int(c.replace("ch", "")) for c in wide.columns]
        downsampled = {
            ch: _zscore(_downsample(wide[f"ch{ch}"].to_numpy(), target))
            for ch in channels
        }
        dtw_mat = np.zeros((len(channels), len(channels)))
        for i, ci in enumerate(channels):
            for j, cj in enumerate(channels):
                if i > j:
                    dtw_mat[i, j] = dtw_mat[j, i]
                    continue
                if i == j:
                    dtw_mat[i, j] = 0.0
                    continue
                dtw_mat[i, j] = _dtw_distance(downsampled[ci], downsampled[cj])
        dtw_df = pd.DataFrame(
            dtw_mat, index=wide.columns.tolist(), columns=wide.columns.tolist()
        )
        dtw_df.to_csv(out_dir / "dtw_16x16.csv")

        # ----- 시각화 -----
        self.stdout.write("[4/4] heatmap PNG 저장")
        _save_heatmap(
            pearson.to_numpy(),
            wide.columns.tolist(),
            "Pearson correlation (16ch watt, 1-week)",
            out_dir / "pearson_heatmap.png",
        )
        # DTW 시각화는 -1~1 범위가 아니라 0~max 정규화 후 표시.
        dtw_norm = dtw_mat / max(dtw_mat.max(), 1e-9)
        _save_heatmap(
            dtw_norm,
            wide.columns.tolist(),
            "DTW distance (normalized, downsampled)",
            out_dir / "dtw_heatmap.png",
        )

        # ----- 요약 통계 -----
        self.stdout.write("")
        self.stdout.write("=== Pearson 카테고리별 평균 ===")
        for k, v in sorted(_category_summary(pearson, channels).items()):
            self.stdout.write(f"  {k:>20s}: {v:+.3f}")

        # top-k 상관 채널쌍 (자기 자신 제외, 절대값 상위 5).
        self.stdout.write("")
        self.stdout.write("=== Pearson 상관 top-5 (절대값 기준) ===")
        rows = []
        for i, ci in enumerate(channels):
            for j, cj in enumerate(channels):
                if i >= j:
                    continue
                rows.append((pearson.iloc[i, j], ci, cj))
        rows.sort(key=lambda r: abs(r[0]), reverse=True)
        for r in rows[:5]:
            corr, ci, cj = r
            self.stdout.write(
                f"  ch{ci:2d}({_category(ci)}) ↔ ch{cj:2d}({_category(cj)}): "
                f"r={corr:+.3f}"
            )

        self.stdout.write("")
        self.stdout.write(f"결과 저장 위치: {out_dir.resolve()}")
