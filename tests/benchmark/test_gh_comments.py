import refagent
import refagent.utils.project_manager as pm
import refagent.benchmark.creation.add_gh_comments as gh_comment


def test_comments_flink():
    project = pm.EvalProject("flink")
    comments = gh_comment.CommentImporter(project=project).get_comments(
        v1_sha="21403e31f4761bdddf5e4e802e0e5eb9b4533202", v2_sha="a6412b8"
    )

    assert len(comments.comments) == 0
    print(comments)


def test_comments_kafka():
    project = pm.EvalProject("kafka")
    comments = gh_comment.CommentImporter(project=project).get_comments(
        v1_sha="a4d6456872dc428dc331d6ea1c6e728648947f98", v2_sha="dd80a90"
    )

    assert len(comments.comments) > 0
    print(comments)
