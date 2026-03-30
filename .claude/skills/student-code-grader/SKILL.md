---
name: student-code-grader
description: Review and grade student programming assignments using automated test results, teacher requirements, and optional rubrics; prioritize execution evidence for correctness, supplement with static analysis; provide teacher-mode or student-mode feedback and assign a fair score from 0 to 100.
---

# Student Code Grader

## Purpose
This skill evaluates student programming assignments in a school or teaching environment.

It reads:
- the teacher's assignment instructions
- the task goals
- the programming language when provided
- the optional rubric or scoring rules
- the student's submitted code
- **automated test results when available** (per-case pass/fail, actual vs expected output, runtime errors, timeouts)
- optional sample input/output, constraints, or test expectations

It then produces:
- a structured evaluation
- a clear explanation of strengths and weaknesses
- **analysis of test failures when execution evidence is present**
- category-level scoring
- a final score from 0 to 100
- audience-appropriate feedback in teacher mode or student mode

## Primary objective
The primary objective is to determine whether the student successfully completed the assigned task.

**When automated test results are provided, correctness is judged primarily from execution evidence.** Static code inspection supplements the analysis by explaining *why* failures occur and identifying issues that tests alone may not reveal (e.g., hardcoding, poor structure, edge cases not covered by the provided test set).

Always prioritize evaluation in this order:
1. task fulfillment
2. correctness (execution evidence first, static analysis second)
3. completeness
4. readability and structure
5. coding style and naming
6. robustness and edge case handling
7. efficiency, but only when performance is relevant to the assignment

## Audience mode
Choose the audience mode from the user's request or infer it from context.

### Teacher mode
Use teacher mode when the user is an instructor, grader, or school administrator.
In teacher mode:
- provide clear grading rationale
- include score breakdown and justification
- distinguish major issues from minor issues
- state assumptions explicitly
- include confidence level for the evaluation
- note rubric ambiguity when relevant
- keep the tone professional and decision-oriented

### Student mode
Use student mode when the user is the student or when the goal is learning-oriented feedback.
In student mode:
- explain mistakes in a constructive and educational way
- emphasize what the student did correctly
- explain what to improve and how to improve it
- avoid overly punitive wording
- still provide a fair score if requested
- keep the tone encouraging but honest

If the audience is unclear, default to teacher mode unless the request clearly asks for coaching or self-improvement feedback.

## Required inputs
Look for the following information:
- assignment title
- assignment requirements
- task objective
- programming language
- student submission
- **automated test results** (if provided by the system)
- optional rubric
- optional sample input/output
- optional constraints
- optional teacher emphasis, such as correctness being more important than style
- optional audience mode: teacher or student

If some information is missing, proceed with reasonable assumptions and state them explicitly.

## Automated test result fields
When the system provides automated test results, the following information may be present:
- total number of test cases
- number passed / failed
- compile error message (if compilation failed)
- per-case details:
  - index
  - status: passed, wrong_answer, runtime_error, timeout, compile_error
  - input fed to the program
  - expected output
  - actual output
  - error message (stderr or timeout details)

## Suggested input template
The preferred input format is:

[Mode]
Teacher or Student

[Assignment Title]
...

[Assignment Requirements]
...

[Task Goal]
...

[Programming Language]
...

[Optional Rubric]
...

[Student Code]
...

[Automated Test Results]
(system-generated, may or may not be present)

## Review process
When grading a submission, follow this process:

1. Understand the assignment
   - identify required functionality
   - identify explicit constraints
   - identify whether formatting, documentation, testing, or efficiency matters

2. **Check automated test results first** (if provided)
   - note overall pass rate
   - identify which cases failed and their failure type
   - note compile errors, runtime errors, or timeouts
   - this is the primary evidence for correctness

3. Read the student code
   - identify what the code is attempting to do
   - identify completed parts, incomplete parts, and missing parts
   - identify how closely the code aligns with the assignment

4. **Correlate test failures with code** (if test results are provided)
   - for each failed case, trace the root cause in the code
   - classify the error type and explain why it fails
   - distinguish between logic errors, boundary errors, format errors, and algorithm errors

5. Evaluate correctness
   - **if test results exist**: base correctness primarily on pass rate and failure analysis
   - **if no test results**: evaluate based on static code inspection, noting uncertainty
   - check the main logic
   - look for incorrect conditions, broken flows, and invalid assumptions

6. Evaluate code quality
   - naming clarity
   - readability
   - structure and organization
   - appropriate use of functions, classes, or modules when relevant
   - unnecessary repetition
   - comments or explanation where relevant

7. Evaluate robustness
   - input handling where appropriate
   - edge case handling where relevant
   - fragile or error-prone logic
   - unsafe patterns when applicable

8. Score the submission
   - use the teacher's rubric if one is provided
   - otherwise use the default scoring rubric in this skill
   - **when test results are present, correctness score must reflect the pass rate**

9. Produce feedback
   - tailor depth and tone to teacher mode or student mode
   - keep the evaluation fair, specific, and consistent with the final score

## Error type analysis strategy
When automated test results contain failures, analyze each failure type using the appropriate strategy:

### wrong_answer
- Compare expected vs actual output character by character
- Look for off-by-one errors, incorrect formula, wrong loop bounds
- Check for output formatting issues (extra spaces, missing newlines, wrong separators)
- Check for partial correctness (some parts of output correct, others wrong)
- Trace the logic path for the failing input through the code

### runtime_error
- Read the error message (segfault, exception, division by zero, etc.)
- Identify which line or operation likely caused the crash
- Check for uninitialized variables, null references, array out-of-bounds
- Check for unhandled edge cases in the input

### timeout
- Identify likely infinite loops or excessive recursion
- Check algorithm complexity vs input size
- Look for missing loop termination conditions
- Check for unnecessary nested loops or redundant computation

### compile_error
- Read the compiler error message
- Identify syntax errors, missing imports, type mismatches
- Note whether the code is substantially complete or barely started

### partial pass (some cases pass, some fail)
- Identify what distinguishes passing cases from failing cases
- Look for edge cases, boundary conditions, or special input patterns
- Check if the algorithm handles small inputs but fails on larger ones

## Default scoring rubric
Use this rubric unless the teacher provides another one:

- Task fulfillment: 30 points
- Correctness: 30 points
- Completeness: 10 points
- Readability and structure: 10 points
- Coding style and naming: 10 points
- Robustness and edge cases: 5 points
- Comments / explanation / clarity: 5 points

Total: 100 points

### Correctness scoring with test results
When automated test results are available, use the pass rate as the primary input for the Correctness dimension:

- All cases pass: 27-30 points (deduct only for hardcoding or obvious cheating)
- 75%+ pass: 20-26 points
- 50-74% pass: 12-19 points
- 25-49% pass: 6-11 points
- <25% pass: 0-5 points
- Compile error (0% pass): 0-3 points (give partial credit only if the code is nearly correct)

These ranges are guidelines. Adjust based on the difficulty distribution of test cases and the nature of failures.

## Deduction guidance
Use these patterns to keep scoring consistent:

- Main requirement not implemented: deduct 10-30 points
- Major logic error in core functionality: deduct 10-25 points
- Partial implementation of important features: deduct 5-15 points
- Poor structure or hard-to-read code: deduct 3-10 points
- Weak naming or style problems: deduct 1-8 points
- Missing edge case handling when clearly necessary: deduct 2-8 points
- Missing comments or explanation when required: deduct 1-5 points

## Score band guidance
Use these general score bands:

- 90-100: Excellent
  - fully or almost fully meets requirements
  - logic is correct or nearly correct
  - code is clear and well-structured
  - only minor issues

- 80-89: Good
  - mostly correct and complete
  - some minor bugs, omissions, or style issues
  - core task is successfully solved

- 70-79: Fair
  - basic task is completed
  - noticeable issues in correctness, completeness, or code quality
  - shows substantial understanding but needs revision

- 60-69: Pass
  - partial fulfillment of the task
  - important mistakes or missing parts
  - shows some understanding but does not fully meet expectations

- 0-59: Needs significant improvement
  - major requirements are not met
  - serious logic errors or incomplete implementation
  - code may not solve the assigned problem

## Execution caution
When **no automated test results** are provided:
- do not claim that code definitely runs, compiles, or produces correct output
- say that the judgment is based on static code inspection
- describe issues as likely, probable, or appears to cause a problem
- do not fabricate test results
- do not invent runtime errors, exact outputs, or performance metrics

When **automated test results are provided**:
- treat them as ground truth for what actually happened at runtime
- do not contradict test results with speculation
- use test evidence as the authoritative source for correctness judgments
- still use static analysis to explain *why* failures occur

## Important grading rules
- Grade against the assignment, not against ideal production software standards
- Be fair and consistent
- Reward correct logic even when style is imperfect
- Penalize heavily when main functionality is wrong or missing
- Do not give a high score to code that is clean but functionally incorrect
- Do not give an extremely low score for small formatting issues alone
- Separate critical issues from minor issues
- Make assumptions explicit
- Keep the written evaluation aligned with the final score
- When assignment requirements conflict with generic style advice, follow the assignment requirements

## Output rules
Always clearly distinguish:
- completed parts
- incomplete parts
- incorrect parts

When appropriate, identify issue severity as:
- Critical
- Major
- Minor

When a custom rubric is provided, follow the custom rubric instead of the default one.

## Output format
Use the appropriate format based on audience mode.

### Teacher mode output

# Code Assignment Review

## 1. Assignment summary
- Brief summary of the task
- Key requirements identified
- Assumptions made

## 2. Automated test results (include only when test results are provided)
- Overall pass rate: X/Y
- Summary of failure types (wrong answer, runtime error, timeout, compile error)
- Per-case analysis for failed cases:
  - What the case tests
  - Why the student's code fails
  - Root cause in the code

## 3. Completion assessment
- Did the student meet the main task objective?
- Which required parts are completed?
- Which parts are incomplete or missing?

## 4. Strengths
- ...

## 5. Issues found
For each issue include:
- Severity: Critical / Major / Minor
- Problem
- Why it matters

## 6. Score breakdown
- Task fulfillment: X/30
- Correctness: X/30
- Completeness: X/10
- Readability and structure: X/10
- Coding style and naming: X/10
- Robustness and edge cases: X/5
- Comments / explanation / clarity: X/5

## 7. Final score
**Total: X/100**

## 8. Feedback for the student
- What was done well
- What should be improved
- Concrete next steps

## 9. Notes for the teacher
- Confidence level: High / Medium / Low
- Whether the evaluation includes automated test evidence or is based on static inspection only
- Any ambiguity caused by unclear requirements

### Student mode output

# Programming Assignment Feedback

## 1. What the assignment asked for
- Brief summary of the task
- Key goals identified
- Assumptions made

## 2. Test results (include only when test results are provided)
- How many tests passed
- What went wrong in failed tests (explained clearly)
- What to look at in your code to fix each failure

## 3. What you did well
- ...

## 4. What needs improvement
For each issue include:
- Severity: Critical / Major / Minor
- What the problem is
- How to improve it

## 5. Score breakdown
- Task fulfillment: X/30
- Correctness: X/30
- Completeness: X/10
- Readability and structure: X/10
- Coding style and naming: X/10
- Robustness and edge cases: X/5
- Comments / explanation / clarity: X/5

## 6. Final score
**Total: X/100**

## 7. Suggested next steps
- ...

## 8. Notes
- Whether this evaluation includes automated test evidence or is based on static code inspection only
- Any uncertainty caused by missing requirements or missing test cases

## Review tone
The review must be:
- fair
- professional
- clear
- specific
- educational
- constructive rather than insulting

Do not use mocking, sarcastic, dismissive, or humiliating language.

## Special instruction
When the request asks for only a short result, still preserve the logic of this skill but compress the wording.
When the request asks for a full grading report, use the full structured format above.
When the request includes multiple student submissions, evaluate them one by one and keep each score clearly separated.
