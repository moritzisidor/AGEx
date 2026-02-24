This repository contains all means to generate and grade **A**uto-**G**rade single-choice **E**xam answer sheets (**AGEx**). \
The code is meant to be executed in a command line interface.

## Usage
1) Clone this repository to your local machine
2) Open command line interface at respective folder

### A - Generate answer sheets
1) Beforehand, execute "python3 generate_answer_sheets.py --help" to get an overview and description of all arguments to be passed.
2) Edit "exam_instructions.tex" w.r.t individual examination regulations on cover sheet.
3) run "python3 create_answer_sheet.py" with respective arguments (experiment with example below).
4) *Output:* answer_sheets/answer_sheet_solution.pdf answer_sheets_all.pdf cover_sheets_all.pdf layout.json


**Example (command line prompt):**\
python3 generate_answer_sheets.py \ \
--paper A4 \ \
--title "Answer sheet" \ \
--course-name "Probability Theory" \ \
--professor "Prof. Pierre-Simon Laplace" \ \
--exam-date "01. Januar 2000" \ \
--num-questions 24 \ \
--options-list 2,2,5,5,3,5,2,3,4,4,5,2,2,2,2,5,2,3,2,3,3,2,2,5 \ \
--columns 5 \ \
--force-columns \ \
--row-gap-mm 4 \ \
--col-gap-mm 14 \ \
--box-size-mm 3.5 \ \
--student-id-start 1 \ \
--student-id-count 4 \ \
--answer-key A,A,D,C,A,D,A,B,D,C,C,B,A,A,B,C,B,C,B,C,A,B,A,E \ \
--cover-tex exam_instructions.tex \ \
--outdir answer_sheets

### B - Scan and grade answer sheets
1) scan and merge (if not default) answer sheets into ONE single multi-page .pdf file.
2) Place "scanned_answer_sheets.pdf" in folder "scans" which was created in Step A.
3) Beforehand, execute "python3 grade_answer_sheets.py --help" to get an overview and description of all arguments to be passed.
4) run "python3 grade_answer_sheets.py" with respective arguments (experiment with example below).
5) *Output:* Student individual results in results.csv

**Example (command line prompt):**\
python3 grade_answer_sheets.py \ \
--layout answer_sheets/layout.json \ \
--scans scans/scanned_answer_sheets.pdf \ \
--student-id-start 1 \ \
--student-id-count 4 \ \
--ambiguity-margin 0.5 \ \
--out results.csv



