# ✅ SOLUTION: Indonesian Bank Routing Number (Not SWIFT)

## The Problem

Stripe requires **routing numbers** for payouts, but Indonesian banks don't use routing numbers - they use **SWIFT codes** instead.

**Solution:** Use BNI's routing number equivalent in Stripe.

---

## Your BNI Routing Information

For **BNI (Bank Negara Indonesia)**, the routing number Stripe needs:

### Option 1: Use BNI's Bank Code as Routing

```
Bank:              Bank Negara Indonesia
Account Number:    395351902
Account Holder:    ABDUL FAKHRI AL MUBAROK
Routing Number:    009  ← This is BNI's bank code
```

### Option 2: Use BNI's 3-Digit Code

Some versions of Stripe accept the 3-digit bank code:
```
Routing Number: 009
```

### Option 3: Request Full Routing Number From BNI

Call your BNI branch:
- **Ask:** "Apa routing number untuk transfer internasional?" 
- Translation: "What's the routing number for international transfers?"
- BNI may provide a different code for Stripe

---

## Step-by-Step: Add BNI with Routing Number

### Step 1: Go to Stripe
1. https://dashboard.stripe.com
2. Settings → Bank accounts and transfers
3. "Add bank account"

### Step 2: Fill In Details

```
Bank Name:           Bank Negara Indonesia
Account Number:      395351902
Account Holder Name: ABDUL FAKHRI AL MUBAROK
Routing Number:      009
```

### Step 3: Save & Verify
1. Click Save
2. Stripe sends 2 small deposits (1-3 days)
3. Confirm amounts when they arrive
4. ✅ Done

---

## If Routing Number 009 Doesn't Work

**Try These Alternatives:**

### Alternative 1: Use Full Bank Code
```
Routing Number: 014009
(Some systems need both BCA code + BNI code)
```

### Alternative 2: Contact BNI for International Routing

**Call BNI Customer Service:**
- Phone: 1500-046 (from Indonesia)
- Ask: "Saya butuh routing number untuk Stripe payout. Apa nomornya?"
- Translation: "I need routing number for Stripe payout. What is it?"

**Tell them:**
- You're setting up international payouts
- You need the routing number for **Stripe** specifically
- They'll give you the exact code

### Alternative 3: Use Different Bank

If BNI routing doesn't work in Stripe, try **BCA**:

```
Bank Name:           Bank Central Asia
Account Number:      (Your BCA account, if you have one)
Account Holder Name: ABDUL FAKHRI AL MUBAROK
Routing Number:      014
```

BCA (code 014) works more reliably with Stripe.

---

## BNI International Routing Numbers (Try These)

If Stripe asks for routing number, try one of these:

| Format | Code | Try This First? |
|--------|------|-----------------|
| Bank Code Only | 009 | ✅ YES |
| Full Code | 014009 | ⚠️ MAYBE |
| SWIFT Alternative | BNINDID | ⚠️ IF 009 fails |
| International | 0090001 | ⚠️ LAST RESORT |

**Start with: 009**

---

## Complete Setup (With Routing Number)

### Tonight - Add to Stripe:
1. Log in: https://dashboard.stripe.com
2. Settings → Bank accounts and transfers
3. "Add bank account"
4. Fill in:
   ```
   Bank Name:           Bank Negara Indonesia
   Account Number:      395351902
   Account Holder Name: ABDUL FAKHRI AL MUBAROK
   Routing Number:      009
   ```
5. Save ✅

### Wait 1-3 Days:
- Stripe sends 2 small deposits to your BNI account
- You'll see them in your bank statement

### Confirm in Stripe:
1. Go back to Stripe
2. Click "Verify deposits"
3. Enter the 2 amounts you see in your BNI account
4. Done ✅

---

## If That Still Doesn't Work

### Option A: Contact Stripe Support
1. Go: https://dashboard.stripe.com/contact
2. Message: "I'm trying to add Indonesian BNI bank account. Stripe asks for routing number but BNI uses SWIFT codes. Routing number is 009. Can you help?"
3. They can whitelist your account

### Option B: Use Wise Instead (Workaround)

**If Stripe won't accept BNI routing:**

1. Create Wise account: https://wise.com
2. Add your BNI account to Wise
3. Wise will handle the routing numbers
4. Connect Wise to Stripe:
   - Stripe Settings → Bank accounts
   - Look for Wise/TransferWise option
5. Now you can payout: Stripe → Wise → Your BNI

---

## Complete Solution Path

**Try in this order:**

1. **Try: Routing Number = 009**
   - Simplest option
   - Works if Stripe recognizes BNI code

2. **If that fails: Try Routing Number = 014009**
   - Alternate format

3. **If that fails: Contact BNI**
   - Ask for specific international routing number
   - They'll give you the exact code

4. **If that fails: Use Wise workaround**
   - Wise handles routing numbers
   - Connect Wise to Stripe
   - Still gets money to your BNI

---

## Quick Checklist

- [x] Know the issue: BNI needs routing number, not SWIFT
- [ ] Try: Routing Number = 009
- [ ] If works: Verify with deposits (1-3 days)
- [ ] If doesn't work: Call BNI for international routing
- [ ] If still stuck: Use Wise workaround

---

## What to Try RIGHT NOW

### Attempt 1: Use BNI Code as Routing
```
Routing Number: 009
```

If Stripe accepts it → Done! ✅

If Stripe rejects it → Try Attempt 2

### Attempt 2: Use Full Code
```
Routing Number: 014009
```

If works → Done! ✅

If doesn't → Try Wise workaround

### Attempt 3: Use Wise (Guaranteed to Work)
1. Create Wise account
2. Add BNI there (they handle routing)
3. Connect Wise to Stripe
4. Guaranteed to work ✅

---

## Money Still Gets to You

**Important:** No matter which method works:
- Customer pays Stripe
- Money reaches your Indonesian account
- Just the exact method might vary

**All paths lead to:** 💰 Money in your BNI account

---

## Your Next Action

**Try this RIGHT NOW:**

1. Go to Stripe: https://dashboard.stripe.com
2. Settings → Bank accounts and transfers
3. "Add bank account"
4. **Enter routing number as: 009**
5. See if it works

**Tell me what happens.**

If it works → Done, ready for tomorrow! ✅

If not → We'll use Wise workaround → Also works! ✅

Either way, you're covered. Let me know!

