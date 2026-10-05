"""The one refusal the forge raises.

A sentence a person can read and a code an agent can branch on, side by side
(spec §11.4): `{"problem": "tile (3, 2) needs 5 colours", "code":
"budget.colours", "asset": "grass", "at": [3, 2]}`. The sentence is what the
bench shows under the button and what the CLI prints; the code is the contract,
and is never reworded once an agent may have learned it.
"""


class ForgeError(ValueError):
    """A request the forge will not carry out, and why.

    `status` is the HTTP status the route answers with: 400 for a request that
    is wrong, 404 for a project or asset that is not there, 409 for one that
    already is.
    """

    def __init__(self, problem, code, status=400, **extra):
        super().__init__(problem)
        self.problem = problem
        self.code = code
        self.status = status
        self.extra = extra

    def answer(self):
        return {"problem": self.problem, "code": self.code, **self.extra}
