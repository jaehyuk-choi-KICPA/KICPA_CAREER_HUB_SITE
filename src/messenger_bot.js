/*
 * 메신저봇R(MessengerBotR) 참조 스크립트 — 폰 측 게시기 (Part B)
 * =================================================================
 * 역할: 랩탑이 발행한 feed.json 을 주기적으로 가져와, 대상 오픈채팅방에
 *       (1) 신규 공고를 개별 메시지로, (2) 일일 다이제스트를 하루 1회 게시.
 *
 * ⚠️ 카카오톡 약관 회색지대 → 반드시 "별도(서브) 카카오 계정"으로 운영.
 * ⚠️ 프로액티브 전송(외부 트리거로 먼저 보내기)이 이 프로젝트의 핵심 난관.
 *    메신저봇R은 기본적으로 "방에서 온 메시지에 응답"하는 구조라, 방에서 한 번이라도
 *    온 메시지에서 replier 를 저장해 둬야 타이머로 먼저 보낼 수 있다.
 *    → 봇 켠 뒤 운영자가 대상 방에 아무 메시지나 1번 보내 replier 를 "워밍업"한다.
 *
 * 설정값 3개만 본인 환경에 맞게 수정하세요.
 */

// ===== 설정 =====
const FEED_URL = "http://192.168.0.10:8777/feed.json"; // 랩탑 LAN IP:포트 (run.py --loop)
const TARGET_ROOM = "CPA 채용 알림방";                  // 게시할 오픈채팅방 이름(정확히)
const POLL_MS = 10 * 60 * 1000;                         // 폴링 주기(밀리초) — 10분
// ================

// 방별 최신 replier 보관(프로액티브 전송용) + 게시 이력(중복 방지)
let repliers = {};                 // roomName -> replier
let postedUids = {};               // uid -> true (이미 게시한 개별 공고)
let lastDigestDate = "";           // 마지막으로 게시한 다이제스트 날짜(yyyy-mm-dd)

// HTTP GET (org.jsoup 사용 — 메신저봇R 내장)
function httpGetJson(url) {
    try {
        const text = org.jsoup.Jsoup.connect(url)
            .ignoreContentType(true)
            .timeout(15000)
            .execute()
            .body();
        return JSON.parse(text);
    } catch (e) {
        Log.e("feed 가져오기 실패: " + e);
        return null;
    }
}

// 대상 방으로 전송(저장된 replier 사용)
function sendToRoom(text) {
    const replier = repliers[TARGET_ROOM];
    if (replier) {
        replier.reply(text);
        return true;
    }
    // 폴백: 일부 버전에서 동작하는 프로액티브 API
    try {
        Api.replyRoom(TARGET_ROOM, text);
        return true;
    } catch (e) {
        Log.e("전송 실패(replier 미확보). 방에 메시지 1번 보내 워밍업 필요: " + e);
        return false;
    }
}

// feed 폴링 → 신규/다이제스트 게시
function poll() {
    const feed = httpGetJson(FEED_URL);
    if (!feed) return;

    // (1) 신규 개별 공고
    const items = feed.new_items || [];
    for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (!it || postedUids[it.uid]) continue;
        if (sendToRoom(it.text)) {
            postedUids[it.uid] = true;
            java.lang.Thread.sleep(1500); // 연속 전송 간 간격(도배 방지)
        }
    }

    // (2) 일일 다이제스트 (날짜가 바뀌었을 때만)
    const digest = feed.digest;
    if (digest && digest.date && digest.date !== lastDigestDate) {
        const chunks = digest.text || [];
        for (let j = 0; j < chunks.length; j++) {
            sendToRoom(chunks[j]);
            java.lang.Thread.sleep(1500);
        }
        lastDigestDate = digest.date;
    }
}

// ===== 메신저봇R 이벤트 =====
// 방에서 메시지가 올 때마다 replier 저장(프로액티브 전송 세션 유지/워밍업)
function response(room, msg, sender, isGroupChat, replier, imageDB, packageName) {
    repliers[room] = replier;
    // 운영자 수동 트리거: 방에 "!update" 입력 시 즉시 폴링
    if (room === TARGET_ROOM && msg.trim() === "!update") {
        poll();
    }
}

// 봇 시작 시 타이머 등록(주기 폴링)
// 참고: 안드로이드 절전으로 타이머가 멈출 수 있어, 폰을 "배터리 최적화 제외"로 설정 권장.
let timer = setInterval(poll, POLL_MS);
