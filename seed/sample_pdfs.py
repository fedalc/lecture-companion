"""Generate small demo slide PDFs (no dependencies) so the app works before real material is added.
Real course PDFs in seed/material/ always take priority; this only runs when that folder is empty.
"""
from pathlib import Path

SAMPLE_COURSE = "Introduction to Machine Learning"
SAMPLE_LECTURER = "Prof. Demo"

SAMPLE_LECTURES = {
    "01_What_is_learning.pdf": [
        ("What is machine learning?", ["A program learns from experience E on task T", "if its performance P on T improves with E.",
                                       "We learn patterns from data instead of writing rules by hand."]),
        ("Supervised learning", ["Training data comes as pairs (input x, label y).", "Goal: learn a function f(x) that predicts y.",
                                 "Classification: y is a category. Regression: y is a number."]),
        ("Unsupervised learning", ["Only inputs x, no labels.", "Goal: find structure, e.g. clusters or lower-dimensional representations.",
                                   "Example: grouping customers by purchase behaviour."]),
        ("Training vs test data", ["We fit the model on the training set.", "We measure performance on a separate test set",
                                   "to estimate how well the model generalises to unseen data."]),
        ("Overfitting", ["A model that memorises training data performs well on training", "but poorly on test data.",
                         "Symptoms: training error low, test error high. Remedies: more data, simpler model, regularisation."]),
    ],
    "02_Linear_regression.pdf": [
        ("Linear regression", ["Model: y_hat = w * x + b", "w is the weight (slope), b is the bias (intercept).",
                               "We choose w and b so predictions are close to the true y."]),
        ("Loss function", ["Mean squared error: MSE = average of (y_hat - y)^2", "Squaring punishes large errors more than small ones.",
                           "Training means finding w, b that minimise the loss."]),
        ("Gradient descent", ["Start with random w, b.", "Repeat: move each parameter a small step against the gradient of the loss.",
                              "w := w - learning_rate * dLoss/dw"]),
        ("Learning rate", ["Too small: training is very slow.", "Too large: the loss oscillates or diverges.",
                           "Typical practice: try values like 0.1, 0.01, 0.001 and watch the loss curve."]),
        ("Feature scaling", ["Features on very different scales make gradient descent zig-zag.",
                             "Standardise each feature: subtract the mean, divide by the standard deviation."]),
    ],
    "03_Classification.pdf": [
        ("Logistic regression", ["Used for binary classification.", "Computes z = w * x + b, then p = sigmoid(z) = 1 / (1 + e^-z).",
                                 "p is the predicted probability of class 1."]),
        ("Decision boundary", ["Predict class 1 if p >= 0.5, i.e. if z >= 0.", "The boundary w * x + b = 0 is a line (or hyperplane).",
                               "Changing the threshold trades precision against recall."]),
        ("Cross-entropy loss", ["Loss = -[y log p + (1 - y) log(1 - p)]", "Confident wrong predictions are punished very strongly.",
                                "MSE is not used because it makes the optimisation non-convex for logistic regression."]),
        ("Precision and recall", ["Precision: of the items predicted positive, how many are positive?",
                                  "Recall: of the truly positive items, how many did we find?",
                                  "Accuracy is misleading when classes are imbalanced."]),
        ("Confusion matrix", ["A 2x2 table of true positives, false positives, false negatives and true negatives.",
                              "Precision = TP / (TP + FP). Recall = TP / (TP + FN)."]),
    ],
}


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, slides: list[tuple[str, list[str]]]) -> None:
    """Minimal landscape PDF, one slide per page, Helvetica text."""
    objs: list[bytes] = []
    n = len(slides)
    page_ids = [3 + i * 2 for i in range(n)]
    font_id = 3 + n * 2
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>".encode())
    for i, (title, lines) in enumerate(slides):
        stream = [f"BT /F1 30 Tf 60 520 Td ({_esc(title)}) Tj ET"]
        y = 450
        for line in lines:
            stream.append(f"BT /F1 18 Tf 70 {y} Td ({_esc('- ' + line)}) Tj ET")
            y -= 40
        stream.append(f"BT /F1 10 Tf 60 30 Td (Slide {i + 1}) Tj ET")
        data = "\n".join(stream).encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>".encode())
        objs.append(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def generate(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, slides in SAMPLE_LECTURES.items():
        p = folder / name
        write_pdf(p, slides)
        paths.append(p)
    return paths
