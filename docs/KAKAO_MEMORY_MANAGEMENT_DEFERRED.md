# 카카오 장기기억 관리 기능 확장안

## 문서 상태

- 상태: **보류(Deferred)**
- 현재 결정: 카카오 사용자의 장기기억은 계속 유지하되, 조회·수정·삭제 UI는 아직 제공하지 않는다.
- 목적: 향후 카카오톡 챗봇 시나리오 안에서 사용자별 기억 관리 기능을 추가할 때 구현 기준으로 사용한다.

이 문서는 현재 HTTP 계약이 아니다. 아래 endpoint와 응답 형식은 구현 시 OpenAPI, 코드, 테스트와
함께 확정해야 한다.

## 현재 동작

```text
KakaoTalk
  -> POST /kakao/skill
  -> AIRE_Kakao
  -> POST /api/v1/integrations/kakao/chat
  -> KakaoIdentityService
  -> 카카오 사용자 전용 Profile의 대화·기억
```

- `bot.id + user.type + botUserKey`를 Backend의 `KAKAO_IDENTITY_PEPPER`로 HMAC 처리해
  결정적인 Profile/Device ID를 만든다.
- 원본 `botUserKey`는 Backend 요청 경계에서만 사용하고 DB와 로그에 저장하지 않는다.
- 카카오 Profile은 `demo-slot-1 / mako / kakao` scope를 사용한다.
- 게임·웹의 `AIRE_OPEN` Profile과 카카오 Profile은 연결되지 않으며 기억도 공유하지 않는다.
- Active Memory는 사용자가 삭제하거나 reset하기 전까지 유지된다. 일반 대화 원문과 기억의
  source 보존 기간은 별도 정책이다.
- 현재 카카오 어댑터는 Chat만 지원한다. 카카오 사용자는 자신의 기억을 조회·수정·삭제하거나
  검토 대기 Candidate를 승인할 수 없다.

여기서 “계속 기억”은 서비스·DB·백업이 유지되고 `KAKAO_IDENTITY_PEPPER`가 바뀌지 않는다는
조건의 운영 정책이다. 영구 보장을 뜻하지 않는다. Pepper를 변경하거나 잃어버리면 같은 카카오
사용자도 새로운 Profile로 인식된다.

## 목표 사용자 흐름

### 1. 기억 목록

1. 사용자가 `내 기억 보여줘`, `기억 관리` 같은 발화를 입력한다.
2. 챗봇 관리자센터의 `기억 관리` 시나리오 블록이 전용 Skill을 호출한다.
3. Adapter가 `bot.id`, `botUserKey`와 목록 요청을 Backend에 전달한다.
4. Backend가 기존 `KakaoIdentityService`로 Profile을 복원하고 그 Profile의 Active Memory만 조회한다.
5. Adapter가 최대 5개 정도의 요약된 항목과 `다음`, `전체 삭제`, `닫기` 버튼을 반환한다.

한 응답에 모든 기억을 넣지 않는다. 기억 본문은 화면 표시용으로 제한 길이까지 자르고,
페이지 이동에는 opaque cursor를 사용한다.

### 2. 개별 삭제

1. 기억 항목의 `삭제` 버튼이 확인 블록을 호출한다.
2. 버튼 `extra`에는 작업 종류와 `memory_id`만 넣는다.
3. 확인 블록에서 `삭제할게요`와 `취소`를 제공한다.
4. 확인 요청을 받은 Backend는 현재 `botUserKey`로 Profile을 다시 구한 뒤 해당 Profile,
   `demo-slot-1`, `mako` 소유의 기억인지 검증하고 삭제한다.
5. 성공하면 삭제 완료를 표시하고 목록으로 돌아갈 수 있게 한다.

`memory_id`만으로 삭제를 허용하지 않는다. 버튼 payload와 `clientExtra`는 신뢰할 수 없는 외부
입력이므로 매 요청마다 인증·신원·scope를 다시 검증한다.

### 3. 전체 초기화

1. `전체 삭제` 버튼은 별도 확인 블록으로 이동한다.
2. 첫 확인에서 삭제 범위를 `카카오에서 마코가 기억한 내용 전체`라고 명확히 표시한다.
3. 두 번째 확인 동작에서만 Backend reset을 호출한다.
4. reset은 현재 카카오 Profile의 `demo-slot-1 / mako`만 대상으로 한다.

게임·웹 `AIRE_OPEN`, 다른 카카오 사용자, 다른 봇의 기억에는 영향을 주면 안 된다.

### 4. 후보 검토

PendingReview Candidate의 목록·승인·거절은 후속 단계로 둔다. 첫 MVP는 Active Memory의
목록·개별 삭제·전체 초기화만 제공한다. 후보 검토까지 한 번에 넣으면 시나리오와 확인 상태가
불필요하게 복잡해진다.

## 카카오 관리자센터 구성안

| 블록 | 역할 | Skill 호출 |
|---|---|---|
| `기억 관리` | 기억 목록 첫 페이지 표시 | 목록 조회 |
| `기억 다음 페이지` | cursor 이후 목록 표시 | 목록 조회 |
| `기억 삭제 확인` | 선택한 기억과 삭제 확인 표시 | 필요 시 상세 조회 |
| `기억 삭제 실행` | 개별 기억 삭제 | 개별 삭제 |
| `기억 전체 삭제 확인` | 전체 삭제 경고 표시 | 없음 |
| `기억 전체 삭제 실행` | 현재 카카오 scope reset | 전체 초기화 |
| `기억 관리 종료` | 일반 대화로 복귀 | 없음 |

카카오 SkillResponse는 `quickReplies` 또는 카드의 `block` action과 `extra`를 사용해 다음 블록을
호출할 수 있다. 전달한 `extra`는 다음 SkillPayload의 `action.clientExtra`에서 읽는다.

참고:

- [카카오 스킬 개념](https://kakaobusiness.gitbook.io/main/tool/chatbot/main_notions/skill)
- [카카오 블록 개념](https://kakaobusiness.gitbook.io/main/tool/chatbot/main_notions/block)
- [카카오 SkillPayload·SkillResponse JSON 형식](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format)
- [카카오 응답 설정](https://kakaobusiness.gitbook.io/main/tool/chatbot/main_notions/setup_answer)

현재 공식 형식 기준으로 SkillResponse `outputs`는 최대 3개, `quickReplies`는 최대 10개다.
응답 크기도 제한되므로 구현 시 실제 봇 테스트로 카드·문자열 길이를 다시 검증한다.

## Backend 확장안

기존 `/api/v1/memories`는 일반 WebClient bearer를 `AIRE_OPEN` Profile로 인증하므로 카카오에서
그대로 호출하면 안 된다. 기존 `/api/v1/integrations/kakao/chat`처럼 Adapter 전용 인증과
카카오 신원 해석을 함께 수행하는 private endpoint가 필요하다.

최소 endpoint 후보:

```text
POST /api/v1/integrations/kakao/memories/list
POST /api/v1/integrations/kakao/memories/delete
POST /api/v1/integrations/kakao/memories/reset
```

공통 요청 경계:

- `Authorization: Bearer <KAKAO_ADAPTER_TOKEN>`
- `bot_id`
- `user.type = botUserKey`
- `user.id = <원본 botUserKey>`
- `X-Request-ID`와 body `request_id` 일치
- 목록은 제한된 `limit`과 opaque cursor만 허용
- 삭제는 `memory_id`와 고정된 사용자 표시용 reason을 사용
- reset은 `demo-slot-1 / mako` 고정 scope만 허용

Backend 처리 순서:

1. Adapter token을 검증한다.
2. `botUserKey` 이외 type을 거부한다.
3. `KakaoIdentityService.resolve()`로 기존과 같은 Profile/Device를 복원한다.
4. 서버가 고정한 `demo-slot-1 / mako` scope로 `MemoryService`를 호출한다.
5. 조회·삭제·reset 결과만 반환하고 내부 Profile/Device ID는 반환하지 않는다.

원본 카카오 ID를 URL, query string, 오류 detail, metric label 또는 로그에 넣지 않는다. 요청 body도
운영 로그에 기록하지 않는다. `KAKAO_ADAPTER_TOKEN`과 `KAKAO_IDENTITY_PEPPER`는 기존과 동일한
secret 관리 정책을 따른다.

## Adapter 확장안

현재 `KakaoSkillPayload`는 `bot`과 `userRequest`만 사용하고 나머지 field를 무시한다. 구현 시
다음만 최소로 추가한다.

- `action.clientExtra`의 허용된 작업 필드 파싱
- 일반 Chat과 기억 관리 작업 라우팅
- 목록용 text/card와 `quickReplies` 생성
- 삭제·reset 확인 응답
- Backend 오류를 성공으로 위장하지 않는 사용자용 실패 응답

허용 operation은 enum으로 제한한다. 예:

```text
list_memories
delete_memory
reset_memories
cancel_memory_action
```

`clientExtra`에 기억 본문, Profile ID, Device ID, 원본 `botUserKey`, token 또는 pepper를 넣지 않는다.

기억 관리 작업은 LLM을 호출하지 않으므로 직접 응답 경로로 처리한다. Callback은 일반 Chat처럼
응답 시간이 실제로 길어질 때만 사용한다.

## 보안·오류 규칙

- `X-Kakao-Skill-Secret`은 Kakao Open Builder에서 Adapter로 오는 요청을 보호한다.
- `KAKAO_ADAPTER_TOKEN`은 Adapter에서 Backend로 가는 요청을 보호한다.
- 두 secret의 역할을 합치거나 카카오 사용자 신원으로 사용하지 않는다.
- 잘못된 token, `accountId`, 소유권이 다른 `memory_id`, 변조된 cursor와 알 수 없는 operation은
  fail-closed로 거부한다.
- 삭제 또는 reset 실패를 완료 메시지로 바꾸지 않는다.
- 같은 삭제 요청 재전송은 이미 삭제된 상태를 안전하게 처리하고 다른 사용자의 존재 여부를
  노출하지 않는다.
- 전체 삭제는 반드시 사용자 확인을 거친다.
- 챗봇 관리자센터의 합성 검증 요청이 `accountId`와 `ignoreMe=true`를 보내더라도 실제 사용자
  Profile로 만들지 않는다. 관리센터 검증 호환이 꼭 필요할 때만 이 조합에 정적인 no-op
  SkillResponse를 반환하는 방식을 별도로 검토한다.

## 테스트 체크리스트

### Backend

- [ ] 같은 `bot.id + botUserKey`는 재시작 후에도 같은 기억 목록을 받는다.
- [ ] 서로 다른 사용자와 서로 다른 bot의 기억이 섞이지 않는다.
- [ ] 다른 Profile의 `memory_id`로 조회·삭제할 수 없다.
- [ ] 개별 삭제 후 검색과 회상 Context에서 즉시 제외된다.
- [ ] reset은 현재 카카오 Profile의 `demo-slot-1 / mako`만 초기화한다.
- [ ] 잘못된 Adapter token, `accountId`, malformed operation과 cursor를 거부한다.
- [ ] 원본 카카오 ID가 DB와 로그에 남지 않는다.
- [ ] 동시·중복 삭제/reset이 부분 성공이나 scope 누출을 만들지 않는다.
- [ ] 기존 `/api/v1/chat`, Kakao Chat, Web Memory API 동작이 그대로다.

### Adapter

- [ ] 일반 발화는 기존 Chat으로 전달된다.
- [ ] 관리 블록의 `clientExtra`만 기억 작업으로 라우팅된다.
- [ ] 목록 없음, 첫/중간/마지막 페이지 응답을 검증한다.
- [ ] 삭제·reset 확인과 취소 흐름을 검증한다.
- [ ] 변조된 `clientExtra`를 거부하고 Backend 실패를 성공으로 표시하지 않는다.
- [ ] 출력 개수, quick reply 개수, 문자열과 전체 응답 크기 제한을 검증한다.
- [ ] Callback 경로에서도 bot/user 정보가 손실되지 않는다.

### 수동 카카오 검증

- [ ] 두 실제 카카오 계정으로 목록과 삭제 격리를 확인한다.
- [ ] 동일 계정 재접속과 서비스 재시작 뒤 연속성을 확인한다.
- [ ] 삭제 취소와 전체 삭제 이중 확인을 확인한다.
- [ ] 챗봇 관리자센터 봇 테스트와 개발 채널에서 응답 형식을 확인한다.

## 권장 구현 순서

1. Backend private 목록 endpoint와 scope 격리 테스트
2. Adapter 목록 라우팅과 `기억 관리` 블록
3. Backend·Adapter 개별 삭제와 확인 블록
4. Backend·Adapter 전체 reset과 이중 확인 블록
5. 실제 카카오 두 계정 격리 smoke
6. 필요할 때만 Candidate 검토와 기억 정정 기능 확장

배포 순서는 Backend, Backend 환경변수 확인, Adapter, 카카오 시나리오 배포 순으로 한다.
Backend private endpoint가 준비되지 않았을 때 일반 `AIRE_WEB` bearer나 `AIRE_OPEN` Profile로
우회하지 않는다.
