import random
import json
from typing import Dict, List, Optional
from datetime import datetime
import pytz

COMMON_RESOLUTIONS = [
    (1920, 1080),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (1280, 720)
]

PLATFORMS = [
    "Windows",
    "macOS",
    "Linux"
]

BROWSERS = {
    "Chrome": {
        "versions": ["120.0.0.0", "119.0.0.0", "118.0.0.0"],
        "brands": [
            {"brand": "Chromium", "version": "120"},
            {"brand": "Google Chrome", "version": "120"},
            {"brand": "Not=A?Brand", "version": "24"}
        ]
    },
    "Firefox": {
        "versions": ["120.0", "119.0", "118.0"],
        "brands": []  # Firefox doesn't use sec-ch-ua
    }
}

COMMON_PLUGINS = [
    "PDF Viewer",
    "Chrome PDF Viewer",
    "Chromium PDF Viewer",
    "Microsoft Edge PDF Viewer",
    "WebKit built-in PDF"
]

LANGUAGES = [
    "en-US",
    "en-GB",
    "en-CA",
    "en-AU"
]

class BrowserProfile:
    def __init__(self, country_code: Optional[str] = None):
        self.screen_size = random.choice(COMMON_RESOLUTIONS)
        self.platform = random.choice(PLATFORMS)
        self.browser_type = random.choice(list(BROWSERS.keys()))
        self.browser_version = random.choice(BROWSERS[self.browser_type]["versions"])
        self.plugins = self._generate_plugins()
        self.language = random.choice(LANGUAGES)
        self.timezone = self._get_timezone(country_code)
        self.color_depth = random.choice([24, 30, 32])
        self.device_memory = random.choice([4, 8, 16])
        self.hardware_concurrency = random.choice([4, 8, 12, 16])
        
        # Generate consistent fingerprint components
        self._generate_fingerprint()

    def _generate_plugins(self) -> List[str]:
        """Generate a realistic set of browser plugins."""
        num_plugins = random.randint(2, 5)
        return random.sample(COMMON_PLUGINS, num_plugins)

    def _get_timezone(self, country_code: Optional[str]) -> str:
        """Get a realistic timezone for the country."""
        if country_code:
            try:
                country_timezones = pytz.country_timezones.get(country_code.upper(), [])
                if country_timezones:
                    return random.choice(country_timezones)
            except Exception:
                pass
        return random.choice(list(pytz.common_timezones))

    def _generate_fingerprint(self):
        """Generate consistent fingerprint components."""
        self.canvas_fp = hash(f"{self.browser_type}{self.browser_version}{self.platform}")
        self.webgl_fp = hash(f"{self.screen_size}{self.platform}{self.browser_type}")
        self.audio_fp = hash(f"{self.browser_type}{self.platform}")

    def get_headers(self, url: str) -> Dict[str, str]:
        """Generate consistent headers for this browser profile."""
        headers = {
            'User-Agent': self._get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': f"{self.language},en;q=0.9",
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1' if random.random() > 0.5 else None,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }

        # Add browser-specific headers
        if self.browser_type == "Chrome":
            headers.update({
                'sec-ch-ua': self._get_browser_brands(),
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': f'"{self.platform}"'
            })

        return {k: v for k, v in headers.items() if v is not None}

    def _get_user_agent(self) -> str:
        """Generate a consistent User-Agent string."""
        if self.browser_type == "Chrome":
            if self.platform == "Windows":
                return f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.browser_version} Safari/537.36'
            elif self.platform == "macOS":
                return f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.browser_version} Safari/537.36'
            else:  # Linux
                return f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.browser_version} Safari/537.36'
        else:  # Firefox
            if self.platform == "Windows":
                return f'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{self.browser_version}) Gecko/20100101 Firefox/{self.browser_version}'
            elif self.platform == "macOS":
                return f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:{self.browser_version}) Gecko/20100101 Firefox/{self.browser_version}'
            else:  # Linux
                return f'Mozilla/5.0 (X11; Linux x86_64; rv:{self.browser_version}) Gecko/20100101 Firefox/{self.browser_version}'

    def _get_browser_brands(self) -> str:
        """Generate sec-ch-ua header value."""
        if self.browser_type != "Chrome":
            return ""
            
        brands = BROWSERS["Chrome"]["brands"]
        brand_strings = [f'"{b["brand"]}";v="{b["version"]}"' for b in brands]
        return ", ".join(brand_strings)

    def get_navigator_info(self) -> Dict:
        """Get consistent navigator properties."""
        return {
            "userAgent": self._get_user_agent(),
            "platform": self.platform,
            "language": self.language,
            "languages": [self.language, "en"],
            "hardwareConcurrency": self.hardware_concurrency,
            "deviceMemory": self.device_memory,
            "screenResolution": self.screen_size,
            "colorDepth": self.color_depth,
            "timezone": self.timezone,
            "plugins": self.plugins
        }

    def get_fingerprint(self) -> Dict:
        """Get consistent fingerprint values."""
        return {
            "canvas": self.canvas_fp,
            "webgl": self.webgl_fp,
            "audio": self.audio_fp,
            "clientRects": hash(f"{self.screen_size}{self.browser_type}")
        } 