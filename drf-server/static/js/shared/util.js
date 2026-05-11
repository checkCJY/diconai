/* ==========================================================
   util.js — 공통 유틸리티
   dashboard.js 에서 공통으로 사용하는 상수·함수 모음
   반드시 dashboard.js 보다 먼저 로드되어야 합니다.
   ========================================================== */

'use strict';

/**
 * 숫자를 2자리 문자열로 패딩 (예: 9 → "09")
 * Header.initClock, Header.updateLastUpdated, nowLabel 에서 공통 사용
 * @param {number} n
 * @returns {string}
 */
const pad = n => String(n).padStart(2, '0');

/** 차트 X축 라벨용 현재 시각 문자열 (HH:MM:SS) */
function nowLabel() {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 최종 갱신 표시용 현재 날짜+시각 문자열 (YYYY.MM.DD HH:MM:SS) */
function nowDateLabel() {
  const d = new Date();
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * Chart.js 실시간 차트에 데이터 포인트 추가
 * 최대 포인트(MAX_POINTS) 초과 시 가장 오래된 항목을 앞에서 제거
 * @param {Chart}  chart   Chart.js 인스턴스
 * @param {string} label   X축 라벨
 * @param {...number} values 각 dataset 에 추가할 값
 */
function pushData(chart, label, ...values) {
  if (!chart || !chart.data || !chart.data.datasets) return;
  if (values.length > chart.data.datasets.length) {
    console.warn('[pushData] values.length > datasets.length',
      { values: values.length, datasets: chart.data.datasets.length });
  }
  chart.data.labels.push(label);
  values.forEach((v, i) => {
    const ds = chart.data.datasets[i];
    if (ds) ds.data.push(v);
  });
  if (chart.data.labels.length > MAX_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets.forEach(ds => ds.data.shift());
  }
  chart.update('none');
}

/** 차트 최대 보관 포인트 수 */
const MAX_POINTS = 30;
