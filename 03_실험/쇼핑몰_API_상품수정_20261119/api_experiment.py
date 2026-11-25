"""본인 실험 상품의 상세설명만 조회·수정·복구한다. 비밀정보를 출력하지 않는다."""

import argparse
import base64
import copy
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local"
EXPECTED_NAME = "[실험용] seelo 아카시아 벌꿀 500g"


class StopExperiment(Exception):
    """대상·원본·응답을 확인하지 못하면 쓰기를 중단한다."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StopExperiment("리디렉션 응답. 인증정보를 다른 주소로 보내지 않고 중단합니다.")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class HtmlStructure(HTMLParser):
    """엔터티 표기·태그 사이 여백만 제외한다. 글자·태그·속성값은 대조한다."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, sorted(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            self.events.append(("end", tag))

    def handle_data(self, data):
        if data.strip():
            self.events.append(("text", data.strip()))


def same_html(first, second):
    return HtmlStructure(first).events == HtmlStructure(second).events


def http(method, url, token=None, payload=None, form=None, headers=None):
    request_headers = dict(headers or {})
    if token:
        request_headers["Authorization"] = "Bearer " + token
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # 원문 응답은 토큰·개인정보가 섞일 수 있으므로 출력하지 않는다.
        raise StopExperiment(f"API HTTP {exc.code}. 쓰기를 자동 재시도하지 않습니다.") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StopExperiment("네트워크 응답을 확인하지 못했습니다. 쓰기를 재전송하지 말고 verify로 재조회하세요.") from None


def naver_token():
    import bcrypt

    config = load(LOCAL / "naver-app.json")
    if config.get("own_store") is not True:
        raise StopExperiment("이 SELF 인증은 본인 소유 실험 스토어 전용입니다.")
    stamp = int(time.time() * 1000)
    signed = bcrypt.hashpw(f"{config['client_id']}_{stamp}".encode(), config["client_secret"].encode())
    result = http("POST", "https://api.commerce.naver.com/external/v1/oauth2/token", form={
        "client_id": config["client_id"], "timestamp": stamp,
        "client_secret_sign": base64.b64encode(signed).decode(),
        "grant_type": "client_credentials", "type": "SELF",
    })
    if not result.get("access_token"):
        raise StopExperiment("토큰 응답에 access_token이 없습니다.")
    save(LOCAL / "naver-token.json", {"access_token": result["access_token"],
         "expires_at": time.time() + result["expires_in"]})
    print("네이버 토큰 발급 완료. 토큰 값은 로컬 파일에만 저장했습니다.")


class ProductApi:
    def __init__(self, platform, product_no):
        if platform not in {"smartstore", "cafe24"} or not re.fullmatch(r"\d{1,19}", str(product_no)):
            raise StopExperiment("플랫폼 또는 상품번호가 올바르지 않습니다.")
        self.platform, self.product_no = platform, str(product_no)
        config = load(LOCAL / ("naver-token.json" if platform == "smartstore" else "cafe24-token.json"))
        if config.get("expires_at", 0) <= time.time():
            raise StopExperiment("토큰이 없거나 만료됐습니다. 인증을 먼저 완료하세요.")
        self.token, self.headers = config["access_token"], {}
        if platform == "smartstore":
            self.url = f"https://api.commerce.naver.com/external/v2/products/origin-products/{product_no}"
        else:
            mall_id = config["mall_id"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", mall_id):
                raise StopExperiment("카페24 몰 ID가 올바르지 않습니다.")
            self.shop_no = int(config.get("shop_no", 1))
            self.headers["X-Cafe24-Api-Version"] = config["api_version"]
            self.url = f"https://{mall_id}.cafe24api.com/api/v2/admin/products/{product_no}"

    def read(self):
        url = self.url + (f"?shop_no={self.shop_no}" if self.platform == "cafe24" else "")
        result = http("GET", url, self.token, headers=self.headers)
        self.guard(result)
        return result

    def guard(self, raw):
        product = raw["originProduct"] if self.platform == "smartstore" else raw["product"]
        name = product.get("name" if self.platform == "smartstore" else "product_name")
        if name != EXPECTED_NAME:
            raise StopExperiment("실험 상품명과 다릅니다. 실제 상품은 수정하지 않습니다.")
        returned_id = product.get("originProductNo" if self.platform == "smartstore" else "product_no")
        if returned_id is None and self.platform == "smartstore":
            # 원상품 상세 응답은 상품번호를 생략한다. 목록 API로 확인한 대상 매핑을 사용한다.
            binding = load(LOCAL / "registered-target.json")
            if binding.get("name") != name:
                raise StopExperiment("등록한 실험 상품의 이름과 다릅니다.")
            returned_id = binding.get("originProductNo")
        if str(returned_id) != self.product_no:
            raise StopExperiment("API 응답 상품번호가 요청과 다릅니다.")
        if self.platform == "cafe24":
            if product.get("selling") != "F" or product.get("display") != "F":
                raise StopExperiment("카페24 판매·진열 안함 상태가 필요합니다.")
        else:
            channel = raw.get("smartstoreChannelProduct", {})
            # 공개 예시몰은 품절·전시중으로 유지한다. 재고가 있는 상품은 허용하지 않는다.
            if (product.get("stockQuantity") != 0
                    or product.get("statusType") not in {"SUSPENSION", "OUTOFSTOCK"}
                    or channel.get("channelProductDisplayStatusType") not in {"SUSPENSION", "ON"}):
                raise StopExperiment("스마트스토어 재고 0·품절 또는 판매중지 상태가 필요합니다.")

    def description(self, raw):
        if self.platform == "smartstore":
            return raw["originProduct"].get("detailContent", "")
        return raw["product"].get("description", "")

    def protected(self, raw):
        if self.platform == "cafe24":
            product = raw["product"]
            keys = ("product_no", "product_name", "price", "retail_price", "selling", "display", "has_option", "product_code")
            return {key: product.get(key) for key in keys}
        product = raw["originProduct"]
        keys = ("originProductNo", "name", "statusType", "salePrice", "stockQuantity", "leafCategoryId", "images", "detailAttribute", "deliveryInfo", "saleStartDate", "saleEndDate")
        return {"originProduct": {key: product.get(key) for key in keys},
                "smartstoreChannelProduct": raw.get("smartstoreChannelProduct")}

    def write(self, fresh, description):
        self.guard(fresh)
        if "실험용 가상 상품" not in description:
            raise StopExperiment("실험용 표시가 없는 본문은 저장하지 않습니다.")
        if self.platform == "cafe24":
            payload = {"shop_no": self.shop_no, "request": {"description": description}}
        else:
            payload = {k: copy.deepcopy(v) for k, v in fresh.items()
                       if k in {"originProduct", "smartstoreChannelProduct", "windowChannelProduct"}}
            payload["originProduct"]["detailContent"] = description
        return http("PUT", self.url, self.token, payload=payload, headers=self.headers)


def verify(api, plan, target):
    current = api.read()
    return {"description_matches": same_html(api.description(current), target),
            "description_exact_match": api.description(current) == target,
            "protected_fields_match": api.protected(current) == plan["protected"],
            "description_sha256": digest(api.description(current))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("naver-token", help="본인 스토어의 인증 토큰을 로컬에 발급")
    prepare = sub.add_parser("prepare", help="API 원본 읽기와 변경안 저장. 쓰지 않음")
    prepare.add_argument("platform", choices=["smartstore", "cafe24"])
    prepare.add_argument("product_no")
    for command in ("apply", "verify", "rollback"):
        action = sub.add_parser(command)
        action.add_argument("run", type=Path)
    args = parser.parse_args()
    if args.command == "naver-token":
        return naver_token()
    if args.command == "prepare":
        api = ProductApi(args.platform, args.product_no)
        original = api.read()
        run = LOCAL / "runs" / f"{datetime.now():%Y%m%dT%H%M%S_%f}_{args.platform}_{args.product_no}"
        save(run / "plan.json", {"platform": args.platform, "product_no": args.product_no,
             "original": original, "original_digest": digest(original),
             "protected": api.protected(original), "before": api.description(original),
             "after": (ROOT / "상세설명_B.html").read_text(encoding="utf-8")})
        print(f"원본·변경안 저장 완료. 아직 쓰지 않았습니다.\n{run}")
        return
    run = args.run.resolve()
    if not run.is_relative_to((LOCAL / "runs").resolve()):
        raise StopExperiment("실험 폴더의 실행 기록만 사용할 수 있습니다.")
    plan = load(run / "plan.json")
    api = ProductApi(plan["platform"], plan["product_no"])
    if args.command == "verify":
        report = {"before": verify(api, plan, plan["before"]), "after": verify(api, plan, plan["after"])}
        save(run / "verification.json", report)
        print(json.dumps(report, ensure_ascii=False))
        return
    fresh = api.read()
    target = plan["after"] if args.command == "apply" else plan["before"]
    if args.command == "apply":
        if (run / "apply-intent.json").exists():
            raise StopExperiment("이 실행의 쓰기 요청 이력이 있습니다. 자동 반복하지 말고 verify로 확인하세요.")
        if digest(fresh) != plan["original_digest"]:
            raise StopExperiment("원본이 바뀌었습니다. 새 prepare가 필요합니다.")
    elif not same_html(api.description(fresh), plan["after"]) or api.protected(fresh) != plan["protected"]:
        raise StopExperiment("현재 값이 실험 적용 결과와 다릅니다. 다른 수정을 덮어쓰지 않습니다.")
    save(run / f"{args.command}-intent.json", {"time": datetime.now().isoformat(), "target_hash": digest(target)})
    api.write(fresh, target)
    report = verify(api, plan, target)
    save(run / f"{args.command}-result.json", report)
    print(json.dumps(report, ensure_ascii=False))
    if not all(report[key] for key in ("description_matches", "protected_fields_match")):
        raise StopExperiment("저장 후 값이 일치하지 않습니다. 재조회와 관리자 확인이 필요합니다.")


if __name__ == "__main__":
    try:
        main()
    except (StopExperiment, FileNotFoundError, KeyError, ValueError) as error:
        if isinstance(error, StopExperiment):
            print(str(error))
        else:
            print("설정·인증 또는 API 응답 형식이 맞지 않습니다. 로컬 파일과 플랫폼 설정을 확인하세요.")
        raise SystemExit(1)
