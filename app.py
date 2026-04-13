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
    response.set_cookie("usage_count", str(usage + 1), httponly=True)
    return response

# -------------------------------
# CREATE ORDER
# -------------------------------
@app.route("/create-order", methods=["POST"])
def create_order():
    try:
        order = razorpay_client.order.create({
            "amount": 9900,  # ₹99
            "currency": "INR",
            "payment_capture": 1
        })
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------
# VERIFY PAYMENT (SECURE 🔒)
# -------------------------------
@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    data = request.get_json()

    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    # 🚨 Basic validation
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return jsonify({"status": "failed", "reason": "missing fields"}), 400

    params_dict = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature
    }

    try:
        # 🔒 Signature verification (CRITICAL)
        razorpay_client.utility.verify_payment_signature(params_dict)

        # ✅ Optional: fetch payment to double verify
        payment = razorpay_client.payment.fetch(razorpay_payment_id)

        if payment["status"] != "captured":
            return jsonify({"status": "failed", "reason": "payment not captured"}), 400

        # ✅ SUCCESS → unlock user
        response = make_response(jsonify({
            "status": "success"
        }))

        # 🍪 Secure cookie
        response.set_cookie(
            "paid_user",
            "true",
            httponly=True,
            samesite="Lax"
        )

        return response

    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 400

# -------------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------------------------------
def handle_ai_request(system_msg, user_msg):

    if not is_paid_user():
        usage = check_usage()
        if usage >= USAGE_LIMIT:
            return None, jsonify({"error": "Free limit reached"}), 403
    else:
        usage = 0

    try:
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

        if not is_paid_user():
            return update_usage(response, usage), None, None

        return response, None, None

    except Exception as e:
        return None, jsonify({"error": str(e)}), 500

# -------------------------------
@app.route("/optimize-resume", methods=["POST"])
def optimize_resume():
    data = request.get_json()
    res, err, code = handle_ai_request(
        "You are a resume optimizer",
        data.get("resume", "")
    )
    if err:
        return err, code
    return res

# -------------------------------
@app.route("/resume-score", methods=["POST"])
def resume_score():
    data = request.get_json()
    res, err, code = handle_ai_request(
        "You are a resume reviewer",
        data.get("resume", "")
    )
    if err:
        return err, code
    return res

# -------------------------------
@app.route("/career-suggestions", methods=["POST"])
def career_suggestions():
    data = request.get_json()
    res, err, code = handle_ai_request(
        "You are a career advisor",
        str(data.get("skills", ""))
    )
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