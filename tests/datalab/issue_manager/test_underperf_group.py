import numpy as np
import pytest

from cleanlab.datalab.internal.issue_manager.underperf_group import UnderperfGroupIssueManager
from sklearn.datasets import make_blobs

SEED = 42


class TestUnderperfGroupIssueManager:
    @pytest.fixture
    def make_data(self, lab, noisy=False):
        def data(noisy=noisy):
            N = lab.get_info("statistics")["num_examples"] * 40
            K = lab.get_info("statistics")["num_classes"] + 1
            features, labels = make_blobs(n_samples=N, centers=K, n_features=2, random_state=SEED)
            pred_probs = np.full((N, K), 0.1)
            pred_probs[np.arange(N), labels] = 0.9
            pred_probs = pred_probs / np.sum(pred_probs, axis=-1, keepdims=True)
            if noisy:  # Swap columns of a class to generate incorrect predictions
                pred_probs_slice = pred_probs[labels == 0]
                pred_probs_slice[:, [0, 1]] = pred_probs_slice[:, [1, 0]]
                pred_probs[labels == 0] = pred_probs_slice
            data = {"features": features, "pred_probs": pred_probs, "labels": labels}
            return data

        return data

    @pytest.fixture
    def issue_manager(self, lab, make_data, monkeypatch):
        data = make_data()
        monkeypatch.setattr(lab._labels, "labels", data["labels"])
        return UnderperfGroupIssueManager(datalab=lab, threshold=0.2)

    def test_find_issues_no_underperf_group(self, issue_manager, make_data):
        data = make_data()
        features, labels, pred_probs = data["features"], data["labels"], data["pred_probs"]
        N = len(labels)
        issue_manager.find_issues(features=features, pred_probs=pred_probs)
        issues, summary = issue_manager.issues, issue_manager.summary
        assert np.sum(issues["is_underperf_group_issue"]) == 0
        expected_issue_mask = np.full(N, False, bool)
        assert np.all(
            issues["is_underperf_group_issue"] == expected_issue_mask
        ), "Issue mask should be correct"
        expected_scores = np.ones(N)
        np.testing.assert_allclose(
            issues["underperf_group_score"], expected_scores, err_msg="Scores should be correct"
        )
        assert summary["issue_type"][0] == "underperf_group"
        assert summary["score"][0] == 1.0

    def test_find_issues(self, issue_manager, make_data):
        data = make_data(noisy=True)
        features, labels, pred_probs = data["features"], data["labels"], data["pred_probs"]
        N = len(labels)
        issue_manager.find_issues(features=features, pred_probs=pred_probs)
        issues, summary = issue_manager.issues, issue_manager.summary
        assert np.sum(issues["is_underperf_group_issue"]) == 50
        expected_issue_mask = np.zeros(N, bool)
        expected_issue_mask[labels == 0] = True
        assert np.all(
            issues["is_underperf_group_issue"] == expected_issue_mask
        ), "Issue mask should be correct"
        expected_loss_ratio = 0.1428
        expected_scores = np.ones(N)
        expected_scores[labels == 0] = expected_loss_ratio
        np.testing.assert_allclose(
            issues["underperf_group_score"],
            expected_scores,
            err_msg="Scores should be correct",
            rtol=1e-3,
        )
        assert summary["issue_type"][0] == "underperf_group"
        assert summary["score"][0] == pytest.approx(expected_loss_ratio, rel=1e-3)

    def test_collect_info(self, issue_manager, make_data):
        data = make_data()
        features, pred_probs = data["features"], data["pred_probs"]
        issue_manager.find_issues(features=features, pred_probs=pred_probs)
        info = issue_manager.info
        assert info["metric"] == "euclidean"
        assert info["HDBSCAN"]["n_clusters"] == 4

    def test_report(self, issue_manager, make_data):
        data = make_data()
        features, pred_probs = data["features"], data["pred_probs"]
        issue_manager.find_issues(features=features, pred_probs=pred_probs)
        report = issue_manager.report(
            issues=issue_manager.issues,
            summary=issue_manager.summary,
            info=issue_manager.info,
        )
        assert isinstance(report, str)
        assert (
            "------------------ underperf_group issues ------------------\n\n"
            "Number of examples with this issue:"
        ) in report
