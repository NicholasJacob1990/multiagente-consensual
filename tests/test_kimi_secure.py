import unittest

from scripts import kimi_secure


class KimiSecureInvocationTests(unittest.TestCase):
    def test_managed_model_stays_selected_and_exposes_opencode_option_in_memory(self):
        inherited = {
            "PATH": "/usr/bin",
            "KIMI_MODEL_PROVIDER_TYPE": "openai",
            "KIMI_MODEL_BASE_URL": "https://stale.invalid/v1",
            "KIMI_MODEL_API_KEY": "stale-secret",
            "KIMI_MODEL_NAME": "stale-model",
        }

        args, environment = kimi_secure.prepare_invocation(
            ["--prompt", "teste"],
            inherited,
            secret_loader=lambda: "test-opencode-secret",
        )

        self.assertEqual(args, ["--model", "kimi-code/k3", "--prompt", "teste"])
        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["KIMI_MODEL_PROVIDER_TYPE"], "openai")
        self.assertEqual(environment["KIMI_MODEL_API_KEY"], "test-opencode-secret")
        self.assertEqual(environment["KIMI_MODEL_NAME"], "kimi-k3")
        self.assertEqual(
            environment["KIMI_MODEL_DISPLAY_NAME"],
            "Kimi K3 · OpenCode Go",
        )

    def test_managed_model_still_starts_when_opencode_key_is_unavailable(self):
        def missing_secret() -> str:
            raise RuntimeError("Keychain indisponível")

        args, environment = kimi_secure.prepare_invocation(
            ["--prompt", "teste"],
            {"PATH": "/usr/bin", "KIMI_MODEL_API_KEY": "stale-secret"},
            secret_loader=missing_secret,
        )

        self.assertEqual(args, ["--model", "kimi-code/k3", "--prompt", "teste"])
        self.assertNotIn("KIMI_MODEL_API_KEY", environment)
        self.assertNotIn("KIMI_MODEL_NAME", environment)

    def test_opencode_model_uses_keychain_only_in_environment(self):
        secret = "test-opencode-secret"
        args, environment = kimi_secure.prepare_invocation(
            ["--model=opencode-go/kimi-k3", "--prompt", "teste"],
            {"PATH": "/usr/bin"},
            secret_loader=lambda: secret,
        )

        self.assertEqual(args, ["--prompt", "teste"])
        self.assertEqual(environment["KIMI_MODEL_PROVIDER_TYPE"], "openai")
        self.assertEqual(environment["KIMI_MODEL_BASE_URL"], "https://opencode.ai/zen/go/v1")
        self.assertEqual(environment["KIMI_MODEL_API_KEY"], secret)
        self.assertEqual(environment["KIMI_MODEL_NAME"], "kimi-k3")
        self.assertNotIn(secret, " ".join(args))

    def test_unknown_model_is_rejected_before_reading_keychain(self):
        def unexpected_secret_read() -> str:
            raise AssertionError("invalid models must fail before reading credentials")

        with self.assertRaisesRegex(RuntimeError, "modelo Kimi não suportado"):
            kimi_secure.prepare_invocation(
                ["--model", "opencode-go/kimi-k2.6", "--prompt", "teste"],
                {},
                secret_loader=unexpected_secret_read,
            )


if __name__ == "__main__":
    unittest.main()
