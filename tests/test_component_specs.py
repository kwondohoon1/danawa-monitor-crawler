import unittest

from danawa_crawler.component_specs import COMPONENTS, extract_component_specs


def spec_page(*items: str, registered: str = "2025.05.") -> str:
    parts = []
    for item in items:
        if ":" in item:
            label, value = item.split(":", 1)
            parts.append(f"<a><u>{label.strip()}</u></a>: <a><u>{value.strip()}</u></a>")
        else:
            parts.append(f"<a><u>{item}</u></a>")
    body = "  / ".join(parts)
    return (
        f'<div class="spec_list"><div class="items">{body}</div></div>'
        f'<div class="made_info"><span class="txt">등록월: {registered}</span></div>'
    )


class ComponentSpecTests(unittest.TestCase):
    def test_gpu_specs(self):
        html = spec_page(
            "RTX 5060",
            "PCIe5.0x16(at x8)",
            "전원 포트: 8핀 x1",
            "가로(길이): 211mm",
            "베이스클럭: 2280",
            "부스트클럭: 2497MHz",
            "스트림 프로세서: 3840",
            "GDDR7",
            "출력단자: DP2.1 , HDMI2.1",
            "사용전력: 145W",
            "2팬",
            "두께: 41mm",
        )
        specs = extract_component_specs(COMPONENTS["gpu"], html, "MANLI 지포스 RTX 5060 Nebula D7 8GB 대원씨티에스")

        self.assertEqual(specs["chipset"], "RTX 5060")
        self.assertEqual(specs["interface"], "PCIe5.0x16(at x8)")
        self.assertEqual(specs["memory_type"], "GDDR7")
        self.assertEqual(specs["memory_size"], "8GB")
        self.assertEqual(specs["boost_clock"], "2497MHz")
        self.assertEqual(specs["stream_processors"], "3840")
        self.assertEqual(specs["power_connector"], "8핀 x1")
        self.assertEqual(specs["length"], "211mm")
        self.assertEqual(specs["power_consumption"], "145W")
        self.assertEqual(specs["fans"], "2팬")
        self.assertEqual(specs["registration_month"], "2025/05")
        self.assertIn("RTX 5060 / PCIe5.0x16(at x8)", specs["full_spec"])

    def test_ram_specs(self):
        html = spec_page(
            "데스크탑용",
            "DDR5",
            "6000MHz (PC5-48000)",
            "램타이밍: CL30-40-40-96",
            "1.35V",
            "램개수: 2개",
            "XMP3.0",
            "온다이ECC",
            "히트싱크: 방열판",
            "높이: 44mm",
        )
        specs = extract_component_specs(
            COMPONENTS["ram"], html, "G.SKILL DDR5-6000 CL30 TRIDENT Z5 J 패키지 (32GB(16Gx2))"
        )

        self.assertEqual(specs["usage"], "데스크탑용")
        self.assertEqual(specs["generation"], "DDR5")
        self.assertEqual(specs["capacity"], "32GB(16Gx2)")
        self.assertEqual(specs["speed"], "6000MHz (PC5-48000)")
        self.assertEqual(specs["timing"], "CL30-40-40-96")
        self.assertEqual(specs["voltage"], "1.35V")
        self.assertEqual(specs["module_count"], "2개")
        self.assertEqual(specs["heatsink"], "방열판")
        self.assertEqual(specs["features"], "XMP3.0 / 온다이ECC")

    def test_ssd_specs(self):
        html = spec_page(
            "M.2 (2280)",
            "PCIe4.0x4 (64GT/s)",
            "TLC",
            "DRAM 탑재",
            "컨트롤러: 파이슨 PS5018-E18",
            "[성능] 순차읽기: 7,300MB/s",
            "순차쓰기: 6,000MB/s",
            "[환경특성] MTBF: 180만",
            "TBW: 1,275TB",
            "A/S기간: 5년 , 제한보증",
            "방열판 포함",
        )
        specs = extract_component_specs(COMPONENTS["ssd"], html, "Seagate Game Drive for PS5 M.2 NVMe (1TB)")

        self.assertEqual(specs["form_factor"], "M.2 (2280)")
        self.assertEqual(specs["interface"], "PCIe4.0x4 (64GT/s)")
        self.assertEqual(specs["capacity"], "1TB")
        self.assertEqual(specs["nand"], "TLC")
        self.assertEqual(specs["dram"], "DRAM 탑재")
        self.assertEqual(specs["controller"], "파이슨 PS5018-E18")
        self.assertEqual(specs["seq_read"], "7,300MB/s")
        self.assertEqual(specs["seq_write"], "6,000MB/s")
        self.assertEqual(specs["mtbf"], "180만")
        self.assertEqual(specs["tbw"], "1,275TB")
        self.assertEqual(specs["warranty"], "5년 , 제한보증")
        self.assertEqual(specs["heatsink"], "방열판 포함")

    def test_spec_fields_are_stable(self):
        for component in COMPONENTS.values():
            fields = component.spec_fields
            self.assertEqual(fields[:4], ["collected_at", "product_code", "product_name", "product_url"])
            self.assertEqual(fields[-4:], ["full_spec", "registration_month", "fetch_status", "error"])
            self.assertEqual(len(fields), len(set(fields)))


if __name__ == "__main__":
    unittest.main()
