import refagent.agents.refactrix.error_fixing as error_fixing


def test_difference_in_errors():

    errors = [
        error_fixing.ErrorMessage(line_num=1, problem="something"),
        error_fixing.ErrorMessage(line_num=2, problem="something else"),
    ]
    error2 = error_fixing.ErrorMessage(line_num=1, problem="something else")

    assert not (error2 in errors)

    error3 = error_fixing.ErrorMessage(line_num=1, problem="something")
    error4 = error_fixing.ErrorMessage(line_num=2, problem="something else")

    assert error3 in errors
    assert error4 in errors
