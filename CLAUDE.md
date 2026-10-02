# Issue tracking via Github

All issues, bugs and planned features are tracked through github issues. If a bug is found that should be fixed separately or a feature has been decided on, check the existing issues for overlaps and edit or comment on existing issues or create a new issue. Never write todos into the code, never create some parallel record inside the repository itself. At most, and only if truly important, document major deficiencies inside the readme with a link to the corresponding github issue.

Note that the github issue list is not exhaustive. Just because a feature isn't in the issue tracker, doesn't mean it is not desired.

# Architecture

It is important to keep the architecture consistent, maintainable and easy to grasp. Modularize where it make sense and keep standard best practices in mind like KISS, DRY, YAGNI and SOLID.

# Development attitude

Try to use the /tdd skill where you can. Always make sure to ask the user about any ambiguities or major decisions.

# Code Quality

Follow standard code quality guidelines. This includes in particular, a clear naming of variables and functions, short function bodies and coherent classes/abstractions.

# Testing

The code should be thoroghly tested. For any added functionality also add corresponding tests. Follow best pracitices for unit testing, among others this includes:

* don't test the same thing over and over again
* never have tests depend on configuration like locale data
* every test focuses on checking exactly one thing
