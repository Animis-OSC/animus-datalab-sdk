import unittest
from datetime import datetime, timezone
from unittest import mock

from animus_sdk import AnimusClient
from animus_sdk.datasets import DatasetRegistryClient
from animus_sdk.experiments import ExperimentsClient
from animus_sdk.git import GitMetadata


class TestPublicContracts(unittest.TestCase):
    def test_experiments_public_api_contracts(self) -> None:
        client = ExperimentsClient(
            gateway_url="https://example.test",
            auth_token="token",
            timeout_seconds=3.0,
        )
        response = {"ok": True}

        with mock.patch("animus_sdk.experiments.request_json", return_value=response) as request:
            self.assertEqual(
                client.create_experiment(
                    name=" premium ",
                    description="desc",
                    metadata={"tier": "aaa"},
                ),
                response,
            )
            self.assertEqual(client.list_experiments(limit=10, name="a&b / c"), response)
            self.assertEqual(
                client.create_run(
                    experiment_id="exp/1",
                    dataset_version_id="dataset/1",
                    status="running",
                    started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    git=GitMetadata(
                        repo="github.com/org/repo",
                        commit="abc",
                        ref="main",
                        source="github",
                    ),
                    params={"lr": 0.1},
                    metrics={"loss": 0.5},
                    artifacts_prefix="runs/a",
                ),
                response,
            )
            with mock.patch(
                "animus_sdk.experiments.get_git_metadata",
                return_value=GitMetadata(
                    repo="github.com/org/repo",
                    commit="def",
                    ref="feature",
                    source="github",
                ),
            ):
                self.assertEqual(
                    client.create_run_with_git(experiment_id="exp-2", status="queued"),
                    response,
                )
            self.assertEqual(
                client.execute_run(
                    experiment_id="exp-3",
                    dataset_version_id="dataset-3",
                    image_ref="ghcr.io/org/train@sha256:abc",
                    git_repo="github.com/org/repo",
                    git_commit="abc",
                    params={"batch": 4},
                    resources={"cpu": "2"},
                ),
                response,
            )
            self.assertEqual(client.get_run(run_id="run/1"), response)
            self.assertEqual(
                client.list_run_artifacts(run_id="run/1", kind="model/checkpoint", limit=25),
                response,
            )
            self.assertEqual(
                client.get_run_artifact(run_id="run/1", artifact_id="artifact/1"),
                response,
            )

        urls = [call.args[1] for call in request.call_args_list]
        self.assertIn(
            "https://example.test/api/experiments/experiments?limit=10&name=a%26b+%2F+c",
            urls,
        )
        self.assertIn(
            "https://example.test/api/experiments/experiment-runs/run%2F1",
            urls,
        )
        self.assertIn(
            "https://example.test/api/experiments/experiment-runs/run%2F1/artifacts/artifact%2F1",
            urls,
        )

    def test_signed_ci_and_artifact_io_contracts(self) -> None:
        client = ExperimentsClient(gateway_url="https://example.test", auth_token="token")

        with mock.patch(
            "animus_sdk.experiments.request_json",
            return_value={"accepted": True},
        ) as request:
            self.assertEqual(
                client.post_ci_webhook(
                    payload={"run_id": "r1", "provider": "github_actions"},
                    ci_secret="secret",
                    ts="1734200000",
                ),
                {"accepted": True},
            )
            self.assertEqual(
                client.post_ci_report(
                    payload={"run_id": "r1", "provider": "github_actions"},
                    ci_secret="secret",
                    ts="1734200000",
                ),
                {"accepted": True},
            )
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertIn("X-Animus-CI-Sig", call.kwargs["headers"])
            self.assertEqual(call.kwargs["headers"]["X-Animus-CI-Ts"], "1734200000")

        with mock.patch(
            "animus_sdk.experiments.download_file",
            return_value={"sha256": "abc", "size_bytes": 3},
        ) as download:
            out = client.download_run_artifact(
                run_id="run/1",
                artifact_id="artifact/1",
                dest_path="/tmp/model.bin",
                max_bytes=1024,
                expected_sha256="0" * 64,
            )
        self.assertEqual(out["size_bytes"], 3)
        self.assertIn("run%2F1", download.call_args.args[1])
        self.assertEqual(download.call_args.kwargs["max_bytes"], 1024)

        with mock.patch(
            "animus_sdk.experiments.upload_multipart_file_json",
            return_value={"artifact_id": "a1"},
        ) as upload:
            out = client.upload_run_artifact(
                run_id="run/1",
                kind="model",
                file_path="/tmp/model.bin",
                name="model",
                metadata={"format": "safetensors"},
            )
        self.assertEqual(out["artifact_id"], "a1")
        self.assertEqual(upload.call_args.kwargs["fields"]["metadata"], '{"format":"safetensors"}')

    def test_dataset_registry_public_api_contracts(self) -> None:
        client = DatasetRegistryClient(
            gateway_url="https://example.test",
            auth_token="token",
            timeout_seconds=2.0,
        )
        with mock.patch(
            "animus_sdk.datasets.request_json",
            return_value={"dataset_version_id": "v1"},
        ) as request:
            out = client.get_dataset_version(dataset_version_id="dataset/version")
        self.assertEqual(out["dataset_version_id"], "v1")
        self.assertEqual(
            request.call_args.args[1],
            "https://example.test/api/dataset-registry/dataset-versions/dataset%2Fversion",
        )

        with mock.patch(
            "animus_sdk.datasets.download_file",
            return_value={"size_bytes": 10, "sha256": "abc"},
        ) as download:
            out = client.download_dataset_version(
                dataset_version_id="dataset/version",
                dest_path="/tmp/dataset.zip",
                max_bytes=2048,
                expected_sha256="0" * 64,
            )
        self.assertEqual(out["size_bytes"], 10)
        self.assertEqual(download.call_args.kwargs["max_bytes"], 2048)
        self.assertIn("dataset%2Fversion", download.call_args.args[1])

    def test_public_client_validation_contracts(self) -> None:
        with self.assertRaises(ValueError):
            AnimusClient(gateway_url="https://user:pass@example.test")
        with self.assertRaises(ValueError):
            AnimusClient(gateway_url="https://example.test?token=secret")
        with self.assertRaises(ValueError):
            AnimusClient(gateway_url="https://example.test", timeout_seconds=0)

        experiments = ExperimentsClient(gateway_url="https://example.test")
        datasets = DatasetRegistryClient(gateway_url="https://example.test")

        with self.assertRaises(ValueError):
            experiments.create_experiment(name=" ")
        with self.assertRaises(ValueError):
            experiments.list_experiments(limit=0)
        with self.assertRaises(ValueError):
            experiments.get_run(run_id="")
        with self.assertRaises(ValueError):
            experiments.list_run_artifacts(run_id="r", limit=0)
        with self.assertRaises(ValueError):
            experiments.post_ci_report(payload={}, ci_secret="")
        with self.assertRaises(ValueError):
            datasets.get_dataset_version(dataset_version_id="")


if __name__ == "__main__":
    unittest.main()
