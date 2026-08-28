import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from animus_sdk.datasets import DatasetRegistryClient
from animus_sdk.experiments import ExperimentsClient


class TestContractAlignment(unittest.TestCase):
    def test_contract_versions(self) -> None:
        self.assertEqual(DatasetRegistryClient.CONTRACT_VERSION, "0.2")
        self.assertEqual(ExperimentsClient.CONTRACT_VERSION, "0.3")

    def test_dataset_registry_crud_urls(self) -> None:
        client = DatasetRegistryClient(gateway_url="https://example.test", auth_token="token")
        with mock.patch("animus_sdk.datasets.request_json", return_value={}) as request:
            client.list_projects(limit=50)
            self.assertEqual(request.call_args.args[:2], ("GET", "https://example.test/api/dataset-registry/projects?limit=50"))

            client.create_project(name="ml", idempotency_key="project-1")
            self.assertEqual(request.call_args.args[:2], ("POST", "https://example.test/api/dataset-registry/projects"))
            self.assertEqual(request.call_args.kwargs["headers"], {"Idempotency-Key": "project-1"})

            client.get_project(project_id="p/1")
            self.assertEqual(request.call_args.args[1], "https://example.test/api/dataset-registry/projects/p%2F1")

            client.list_datasets(limit=25)
            self.assertEqual(request.call_args.args[1], "https://example.test/api/dataset-registry/datasets?limit=25")

            client.create_dataset(name="fraud", metadata={"owner": "ml"})
            self.assertEqual(request.call_args.kwargs["json_body"]["name"], "fraud")

            client.get_dataset(dataset_id="d1")
            self.assertEqual(request.call_args.args[1], "https://example.test/api/dataset-registry/datasets/d1")

            client.list_dataset_versions(dataset_id="d1", limit=10)
            self.assertEqual(
                request.call_args.args[1],
                "https://example.test/api/dataset-registry/datasets/d1/versions?limit=10",
            )

    def test_dataset_upload_maps_multipart_contract(self) -> None:
        client = DatasetRegistryClient(gateway_url="https://example.test")
        with TemporaryDirectory() as td:
            file_path = Path(td) / "dataset.zip"
            file_path.write_bytes(b"zip")
            with mock.patch("animus_sdk.datasets.upload_multipart_file_json", return_value={"version_id": "v1"}) as upload:
                out = client.upload_dataset_version(
                    dataset_id="d1",
                    file_path=str(file_path),
                    metadata={"split": "train"},
                    quality_rule_id="q1",
                    idempotency_key="upload-1",
                )
        self.assertEqual(out["version_id"], "v1")
        self.assertEqual(upload.call_args.args[:2], ("POST", "https://example.test/api/dataset-registry/datasets/d1/versions/upload"))
        self.assertEqual(upload.call_args.kwargs["headers"], {"Idempotency-Key": "upload-1"})
        self.assertEqual(json.loads(upload.call_args.kwargs["fields"]["metadata"]), {"split": "train"})
        self.assertEqual(upload.call_args.kwargs["fields"]["quality_rule_id"], "q1")

    def test_limits_follow_openapi_bounds(self) -> None:
        datasets = DatasetRegistryClient(gateway_url="https://example.test")
        experiments = ExperimentsClient(gateway_url="https://example.test")
        with self.assertRaises(ValueError):
            datasets.list_datasets(limit=501)
        with self.assertRaises(ValueError):
            experiments.list_experiments(limit=501)
        with self.assertRaises(ValueError):
            experiments.list_run_metrics(run_id="r1", limit=1001)

    def test_experiments_read_surfaces(self) -> None:
        client = ExperimentsClient(gateway_url="https://example.test", auth_token="token")
        with mock.patch("animus_sdk.experiments.request_json", return_value={}) as request:
            client.get_experiment(experiment_id="e1")
            self.assertEqual(request.call_args.args[1], "https://example.test/api/experiments/experiments/e1")

            client.list_experiment_runs(experiment_id="e1", limit=20)
            self.assertEqual(request.call_args.args[1], "https://example.test/api/experiments/experiments/e1/runs?limit=20")

            client.list_runs(limit=30, status="running", active=True)
            self.assertEqual(
                request.call_args.args[1],
                "https://example.test/api/experiments/experiment-runs?limit=30&status=running&active=true",
            )

            client.get_run_execution(run_id="r1")
            self.assertEqual(request.call_args.args[1], "https://example.test/api/experiments/experiment-runs/r1/execution")

            client.get_run_build_context(run_id="r1")
            self.assertEqual(request.call_args.args[1], "https://example.test/api/experiments/experiment-runs/r1/build-context")

            client.list_run_metrics(run_id="r1", name="loss", limit=100)
            self.assertEqual(
                request.call_args.args[1],
                "https://example.test/api/experiments/experiment-runs/r1/metrics?limit=100&name=loss",
            )

    def test_canonical_dispatch_uses_project_scoped_api(self) -> None:
        client = ExperimentsClient(gateway_url="https://example.test")
        with mock.patch("animus_sdk.experiments.request_json", return_value={"dispatchId": "dp1"}) as request:
            out = client.dispatch_run(project_id="p/1", run_id="r:1", idempotency_key="dispatch-1")
        self.assertEqual(out["dispatchId"], "dp1")
        self.assertEqual(
            request.call_args.args[:2],
            ("POST", "https://example.test/api/experiments/projects/p%2F1/runs/r%3A1%3Adispatch"),
        )
        self.assertEqual(request.call_args.kwargs["json_body"], {"idempotencyKey": "dispatch-1"})

    def test_legacy_execute_run_remains_compatible(self) -> None:
        client = ExperimentsClient(gateway_url="https://example.test")
        with mock.patch("animus_sdk.experiments.request_json", return_value={}) as request:
            client.execute_run(experiment_id="e1", dataset_version_id="v1", image_ref="repo/image@sha256:abc")
        self.assertEqual(request.call_args.args[1], "https://example.test/api/experiments/experiments/runs%3Aexecute")


if __name__ == "__main__":
    unittest.main()
