"""실제 BrowserProduct로 본문을 잠시 변경하고 재조회·공개 확인 후 복구한다."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.domain.commerce import fingerprint, normalize_cafe24_browser_html  # noqa: E402
from seelo.integrations.browser.commerce import BrowserProduct  # noqa: E402
from seelo.integrations.browser.session import BrowserSession  # noqa: E402


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def public_check(client, url, marker, output, stage):
    async with BrowserSession(client.platform, profile_path=client.profile) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if stage == "applied":
            await page.get_by_text(marker, exact=True).scroll_into_view_if_needed(timeout=15000)
        else:
            await page.locator("body").wait_for()
        visible = marker in await page.locator("body").inner_text()
        await page.screenshot(path=str(output / f"{stage}_public.png"))
        return visible


async def main(args):
    output = Path(args.output)
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    client = BrowserProduct(args.platform, args.external_id, args.shop_no)
    before_file = output / "before.json"
    if before_file.exists():
        if not args.restore_only:
            raise RuntimeError("기존 시험 기록이 있습니다. 재전송하지 않습니다.")
        before = json.loads(before_file.read_text(encoding="utf-8"))
    else:
        if args.restore_only:
            raise RuntimeError("복구할 원본이 없습니다.")
        before = await client.fetch(args.product_no)
        save(before_file, before)
    marker = "seelo 브라우저 자동수정 검증 2026-11-24"
    original = before["fields"]["description"]
    proposed = original + f"\n<p>{marker}</p>"
    result = {"platform": args.platform, "product_no": args.product_no, "before_hash": fingerprint(before)}
    save(output / "intent.json", {**result, "proposed": proposed, "status": "prepared"})
    try:
        if not args.restore_only:
            await client.write(args.product_no, before, {"description": proposed})
            after = await client.fetch(args.product_no)
            save(output / "after.json", after)
            result["readback_exact"] = after["fields"]["description"] == proposed
            result["readback_trim_equal"] = after["fields"]["description"].strip() == proposed.strip()
            normalized = normalize_cafe24_browser_html if args.platform == "cafe24" else lambda value: value
            result["readback_normalized_equal"] = normalized(after["fields"]["description"]) == normalized(
                proposed
            )
            result["protected_unchanged"] = before["protected"] == after["protected"]
            result["public_marker"] = await public_check(client, args.public_url, marker, output, "applied")
            save(output / "result.json", result)
    finally:
        current = await client.fetch(args.product_no)
        description = current["fields"]["description"]
        if description.strip() == original.strip():
            result["restored_exact"] = description == original
            result["restored_trim_equal"] = True
        elif (
            marker in description and description.replace(f"<p>{marker}</p>", "").strip() == original.strip()
        ):
            await client.write(args.product_no, current, {"description": original})
            restored = await client.fetch(args.product_no)
            save(output / "restored.json", restored)
            result["restored_exact"] = restored["fields"]["description"] == original
            result["restored_trim_equal"] = restored["fields"]["description"].strip() == original.strip()
            result["restored_protected"] = restored["protected"] == before["protected"]
        else:
            result["restore_conflict"] = True
        if result.get("restored_trim_equal"):
            result["public_marker_after_restore"] = await public_check(
                client, args.public_url, marker, output, "restored"
            )
        save(output / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["cafe24", "smartstore"], required=True)
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--product-no", required=True)
    parser.add_argument("--shop-no", type=int, default=1)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--restore-only", action="store_true")
    asyncio.run(
        main(parser.parse_args()),
        loop_factory=asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.new_event_loop,
    )
