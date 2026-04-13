from flask import Flask, request, jsonify, render_template, make_response
import os
from dotenv import load_dotenv
from openai import OpenAI
import razorpay

# -------------------------------
# Load env
# -------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY missing")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise ValueError("Razorpay keys missing")

# -------------------------------
# Clients
# -------------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

# -------------------------------
# App
# -------------------------------
app = Flask(__name__)

USAGE_LIMIT = 2

# -------------------------------
# Helpers
# -------------------------------
def is_paid_user():
    return request.cookies.get("paid_user") == "true"

def check_usage():
    return int(request.cookies.get("usage_count", 0))

def update_usage(response, usage):
    response.set_cookie(
        "usage_count",
        str(usage + 1),
        max_age=60*60*24,  # 1 day
        httponly=True,
        secure=True,              # 🔥 REQUIRED FOR HTTPS (Render)
        samesite="None"           # 🔥 REQUIRED FOR cross-site
    )
    return response

def set_paid_user(response):
    response.set_cookie(
        "paid_user",
        "true",
        max_age=60*60*24*30,  # 30 days
        httponly=True,
        secure=True,          # 🔥 REQUIRED
        samesite="None"       # 🔥 REQUIRED
    )
    return response

# -------------------------------
# Payment Route
# -------------------------------
@app.route("/create-order", methods=["POST"])
def create_order():
    try:
        order = razorpay_client.order.create({
            "amount": 9900,
            "currency": "INR",
            "payment_capture": 1
        })
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Verify Payment
# -------------------------------
@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    data = request.get_json()

    params_dict = {
        'razorpay_order_id': data.get('razorpay_order_id'),
        'razorpay_payment_id': data.get('razorpay_payment_id'),
        'razorpay_signature': data.get('razorpay_signature')
    }

    try:
        razorpay_client.utility.verify_payment_signature(params_dict)

        response = make_response(jsonify({"status": "success"}))
        return set_paid_user(response)

    except Exception:
        return jsonify({"status": "failed"}), 400

# -------------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------------------------------
def handle_ai_request(system_msg, user_msg):

    paid = is_paid_user()
    usage = check_usage()

    # DEBUG (optional)
    print("PAID:", paid, "USAGE:", usage)

    if not paid and usage >= USAGE_LIMIT:
        return None, jsonify({"error": "Free limit reached"}), 403

    response_ai = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]
    )

    response = make_response(jsonify({
        "result": response_ai.choices[0].message.content
    }))

    if not paid:
        return update_usage(response, usage), None, None

    return response, None, None

# -------------------------------
@app.route("/optimize-resume", methods=["POST"])
def optimize_resume():
    data = request.get_json()
    res, err, code = handle_ai_request("You are a resume optimizer", data.get("resume", ""))
    if err:
        return err, code
    return res

# -------------------------------
@app.route("/resume-score", methods=["POST"])
def resume_score():
    data = request.get_json()
    res, err, code = handle_ai_request("You are a resume reviewer", data.get("resume", ""))
    if err:
        return err, code
    return res

# -------------------------------
@app.route("/career-suggestions", methods=["POST"])
def career_suggestions():
    data = request.get_json()
    res, err, code = handle_ai_request("You are a career advisor", str(data.get("skills", "")))
    if err:
        return err, code
    return res

# -------------------------------
@app.route("/skill-gap", methods=["POST"])
def skill_gap():
    data = request.get_json()
    res, err, code = handle_ai_request(
        "You are a career coach",
        f"{data.get('skills','')} → {data.get('role','')}"
    )
    if err:
        return err, code
    return res

# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)