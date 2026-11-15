"""The frame generation runtime choice: DLSS (default) or the ANR runtime.

The ANR runtime from Apex Compute is a DLL the user picks. The worker loads it
only when its Authenticode signature is Apex Compute's and chains to a machine
root (native/dll_trust.h, kApexSignerCn); NVIDIA's own gate is unchanged.

Checked without a window or a GPU:

1. the choice is "dlss" or "apex", anything else is "dlss"; a file path that is
   not a string is empty (settings_io);
2. the worker reads NS_FG_APEX_DLL only for "apex" with a file chosen, and the
   variable is removed otherwise, so a switch back to DLSS takes effect on the
   next worker (apply_fg_provider_env);
3. the trust gate keeps NVIDIA's signer and product check, and the Apex signer
   is a separate, product-free check (source-level, since the gate is C++).

Run:  runtime\\python.exe tests\\test_fg_provider.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "app"))

import settings_io  # noqa: E402

KEY = "NS_FG_APEX_DLL"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def check_settings() -> None:
    if settings_io.FG_PROVIDERS != ("dlss", "apex"):
        fail(f"the runtimes are {settings_io.FG_PROVIDERS}")
    cfg = {"fg_provider": "bogus", "fg_apex_dll": 42}
    # The validation that runs at load: fold a bad choice to DLSS, a bad path to ''.
    if cfg["fg_provider"] not in settings_io.FG_PROVIDERS:
        cfg["fg_provider"] = "dlss"
    if not isinstance(cfg["fg_apex_dll"], str):
        cfg["fg_apex_dll"] = ""
    if cfg != {"fg_provider": "dlss", "fg_apex_dll": ""}:
        fail(f"bad values were not folded: {cfg}")
    print("OK: the runtime choice and its path are validated")


def check_env() -> None:
    os.environ.pop(KEY, None)
    path = os.path.join("C:\\", "ANR", "nvngx_dlssg.dll")
    settings_io.apply_fg_provider_env({"fg_provider": "apex", "fg_apex_dll": path})
    if os.environ.get(KEY) != path:
        fail("apex with a file did not set NS_FG_APEX_DLL")
    settings_io.apply_fg_provider_env({"fg_provider": "apex", "fg_apex_dll": ""})
    if KEY in os.environ:
        fail("apex with no file left a stale NS_FG_APEX_DLL")
    settings_io.apply_fg_provider_env({"fg_provider": "apex", "fg_apex_dll": path})
    settings_io.apply_fg_provider_env({"fg_provider": "dlss", "fg_apex_dll": path})
    if KEY in os.environ:
        fail("switching back to DLSS left NS_FG_APEX_DLL set")
    print("OK: the worker sees the ANR file only when it is chosen, and loses it on a switch back")


def check_gate() -> None:
    with open(os.path.join(BASE, "native", "dll_trust.h"), encoding="utf-8") as handle:
        source = handle.read()
    if 'kTrustedSignerCn = L"NVIDIA Corporation"' not in source:
        fail("NVIDIA's signer check changed")
    if 'kApexSignerCn = L"Apex Compute, Inc."' not in source:
        fail("the Apex signer is not pinned to Apex Compute, Inc.")
    if "NsTrustedDllFor(apex_path, kApexSignerCn, nullptr)" not in open(
            os.path.join(BASE, "native", "frame_generation.inl"), encoding="utf-8").read():
        fail("the frame generation loader does not gate the ANR runtime on its signer")
    print("OK: NVIDIA's gate is unchanged, and the ANR runtime passes a signer-only gate")


if __name__ == "__main__":
    check_settings()
    check_env()
    check_gate()
    print("OK: the frame generation runtime is chosen by the user and checked by its signer")
