"""실제 상품·판매 중 상품 차단과 본문 외 필드 보존을 검사한다."""

import copy
import unittest
from unittest.mock import patch

from api_experiment import EXPECTED_NAME, ProductApi, StopExperiment, same_html


class WriteBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.api = ProductApi.__new__(ProductApi)
        self.api.platform, self.api.product_no = "smartstore", "123"
        self.api.token, self.api.headers, self.api.url = "검사용", {}, "https://api.commerce.naver.com/external/v2/products/origin-products/123"
        self.raw = {
            "originProduct": {"originProductNo": 123, "name": EXPECTED_NAME,
                "detailContent": "실험용 가상 상품 A", "stockQuantity": 0,
                "salePrice": 14900, "statusType": "SUSPENSION",
                "detailAttribute": {"optionInfo": {"useStockManagement": False}}},
            "smartstoreChannelProduct": {"channelProductDisplayStatusType": "SUSPENSION",
                "naverShoppingRegistration": False},
        }

    def test_real_product_rejected(self):
        self.raw["originProduct"]["name"] = "일반 판매 상품"
        with self.assertRaises(StopExperiment):
            self.api.guard(self.raw)

    def test_purchasable_or_unknown_status_rejected(self):
        for path, key, value in (("originProduct", "stockQuantity", 1),
                                 ("originProduct", "statusType", "SALE"),
                                 ("originProduct", "statusType", "WAIT"),
                                 ("smartstoreChannelProduct", "channelProductDisplayStatusType", "UNKNOWN")):
            raw = copy.deepcopy(self.raw)
            raw[path][key] = value
            with self.assertRaises(StopExperiment):
                self.api.guard(raw)

    def test_public_sold_out_example_is_allowed(self):
        self.raw["originProduct"]["statusType"] = "OUTOFSTOCK"
        self.raw["smartstoreChannelProduct"]["channelProductDisplayStatusType"] = "ON"
        self.api.guard(self.raw)
        with patch("api_experiment.http", return_value={}) as send:
            self.api.write(self.raw, "실험용 가상 상품 B")
        sent = send.call_args.kwargs["payload"]
        self.assertEqual(sent["originProduct"]["stockQuantity"], 0)
        self.assertEqual(sent["originProduct"]["statusType"], "OUTOFSTOCK")
        self.assertEqual(sent["smartstoreChannelProduct"]["channelProductDisplayStatusType"], "ON")

    def test_other_product_number_rejected(self):
        self.raw["originProduct"]["originProductNo"] = 124
        with self.assertRaises(StopExperiment):
            self.api.guard(self.raw)

    def test_write_changes_only_description(self):
        original = copy.deepcopy(self.raw)
        with patch("api_experiment.http", return_value={}) as send:
            self.api.write(self.raw, "실험용 가상 상품 B")
        sent = send.call_args.kwargs["payload"]
        self.assertEqual(sent["originProduct"].pop("detailContent"), "실험용 가상 상품 B")
        original["originProduct"].pop("detailContent")
        self.assertEqual(sent, original)
        self.assertEqual(self.raw["originProduct"]["detailContent"], "실험용 가상 상품 A")

    def test_unmarked_description_rejected(self):
        with self.assertRaises(StopExperiment):
            self.api.write(self.raw, "실제 판매 문구")


class HtmlVerificationTest(unittest.TestCase):
    def test_entity_and_table_indentation_are_equivalent(self):
        first = '<div style="font-family:\'Malgun Gothic\'"><table>\n <tbody><tr><td>500g</td></tr></tbody>\n</table><img src="https://example.com/a.png" /></div>'
        second = '<div style="font-family:&#39;Malgun Gothic&#39;"><table><tbody><tr><td>500g</td></tr></tbody></table><img src="https://example.com/a.png"></div>'
        self.assertTrue(same_html(first, second))

    def test_content_image_and_layout_changes_are_detected(self):
        original = '<p style="font-size:17px">500g</p><img src="https://example.com/a.png">'
        for changed in (original.replace('500g', '600g'), original.replace('a.png', 'b.png'), original.replace('17px', '12px')):
            self.assertFalse(same_html(original, changed))


if __name__ == "__main__":
    unittest.main()
