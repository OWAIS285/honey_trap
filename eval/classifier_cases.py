"""Hand-written calls for the classifier: ordinary ones that must not be flagged, scams that must be.

Used by eval/classifier_check.py (live model) and tests/test_classifier_cases.py (shape only).
"""

C, P = "caller", "persona"

ORDINARY = {
    "wrong_number": [(C, "Hello, is this Sunita?"), (P, "No, you have the wrong number."), (C, "Oh sorry, I wanted the tailor shop.")],
    "friend_walk": [(C, "Namaste Sharma ji, Verma here from the park. Are you coming for the morning walk tomorrow?")],
    "delivery_address": [(C, "Sir, I am the delivery boy. I am near Nirala Nagar, which house is yours? Is there any landmark?")],
    "asks_phone_number": [(C, "Sir, can you tell me your phone number? I want to save it."), (P, "I would rather not give my number on the phone."), (C, "Thank you, and what is your name?")],
    "bank_branch_visit": [(C, "Sir, I am calling from the State Bank Aliganj branch. Your passbook update is pending. Please visit any day this week, there is no hurry.")],
    "survey": [(C, "Hello sir, a short survey on electricity supply in Lucknow. Was the power supply good last month?")],
    "family_hinglish": [(C, "Papa, Amit bol raha hoon. Kaise hain aap? Dawai li aapne?")],
    "quiz_question": [(C, "Uncle, my daughter has a quiz. What is the capital of France?")],
    "clinic": [(C, "Sir, this is Dr. Mehta's clinic. Your appointment is tomorrow at eleven. Please confirm you are coming.")],
    "neighbour_repays": [(C, "Sharma ji, I want to return the two thousand rupees I borrowed. Can you tell me your account number and bank? I will send it by UPI.")],
    "greeting_only": [(C, "Hello? Hello? Can you hear me?")],
    "gas_agency_hindi": [(C, "नमस्ते शर्मा जी, मैं गैस एजेंसी से बोल रहा हूँ। आपका सिलेंडर कल सुबह आ जाएगा।")],
    "polite_marketing": [(C, "Hello sir, we have a new broadband plan at four ninety nine rupees a month. Would you like to hear about it?")],
    "asks_bank_name": [(C, "Sir, which bank do you have your pension in? My father is also looking for a good one."), (P, "State Bank, Aliganj branch."), (C, "Good, thank you. And how is the weather in Lucknow?")],
}

SCAMS = {
    "digital_arrest": [
        (C, "This is Officer Rajiv Malhotra from CBI. A parcel in your name was caught with illegal drugs and there is an arrest warrant."),
        (P, "What? Please, I am an old man."),
        (C, "Do not tell anyone and stay on the line. Transfer fifty thousand rupees as a security deposit to this UPI ID right now."),
    ],
    "bank_kyc_otp": [(C, "Sir, your SBI account will be blocked today because your KYC is pending. Share the OTP that you will receive to update it.")],
    "lottery_fee": [(C, "Congratulations, you have won twenty five lakh in the KBC lottery. To claim it, pay a processing fee of twelve thousand rupees on UPI today.")],
    "remote_access": [(C, "I am calling from Microsoft support, your computer has a virus. Install AnyDesk now and tell me the nine digit code.")],
    "courier_clearance": [(C, "This is FedEx. Your parcel has illegal items. Pay the clearance charge of eighteen thousand five hundred to this account today or the police will come to your house.")],
    "electricity_hinglish": [(C, "Sir aapka bijli connection raat 9 baje kat jayega kyunki bill pending hai. Abhi is number pe bhejiye aur ye app download kijiye.")],
    "grandson_accident": [(C, "Dadaji, I am your grandson, I have had an accident. Please do not tell papa, send forty thousand rupees to this UPI immediately.")],
    "task_job": [(C, "Work from home, earn five thousand rupees daily by liking videos. First deposit three thousand to join the premium task group on Telegram.")],
    "loan_threat": [(C, "Your loan is overdue. We will send your photos to every contact in your phone unless you pay fifteen thousand rupees right now.")],
    "crypto_returns": [(C, "Guaranteed forty percent returns every week on our crypto platform. Transfer one lakh today, only two slots left.")],
    "cvv_for_refund": [(C, "Sir I am from the bank. To cancel the fraud transaction, tell me the CVV and expiry date of your debit card.")],
    "slow_burn": [
        (C, "Hello sir, I am calling from the telecom department."),
        (P, "Yes? Which department?"),
        (C, "Your SIM card will be disconnected in two hours because of illegal activity. Do not hang up, do not tell anyone."),
        (P, "Oh no, what should I do?"),
        (C, "Pay the verification charge of nine thousand rupees to this account, then your SIM stays active."),
    ],
}


def to_turns(call: list[tuple[str, str]]) -> list[dict]:
    return [{"n": i, "speaker": speaker, "text": text, "tSec": i} for i, (speaker, text) in enumerate(call, 1)]
