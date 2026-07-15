# 🔧 TROUBLESHOOTING: Can't Add Indonesian Bank to Stripe

## Why This Happens

Stripe has strict requirements for Indonesian banks. Common issues:

1. **Country not set to Indonesia**
2. **Bank name format wrong**
3. **Account number format wrong**
4. **Missing bank routing code**
5. **BNI not in Stripe's supported list**
6. **Account type mismatch**

---

## Solution 1: Check Your Account Country (CRITICAL)

### Step 1: Verify Country Setting
1. Log into Stripe: https://dashboard.stripe.com
2. Click: **Settings** (⚙️ icon)
3. Click: **Account settings** or **Business profile**
4. Look for: **"Country"** or **"Business location"**
5. Make sure it says: **Indonesia** 🇮🇩

**If it says USA or anything else:**
- Click to change it
- Select: **Indonesia**
- Save

### Step 2: Check Stripe Account Type
1. Still in Settings
2. Look for: **Account status** or **Account type**
3. Should show: **Individual** or **Business**

---

## Solution 2: Correct Bank Information Format

### Try This Format Instead:

**Do NOT use:**
- Bank Name: "Bank Negara Indonesia" (too long)
- Bank Name: "BNI" (too short)

**Use:**
- Bank Name: **"PT Bank Negara Indonesia (Persero) Tbk"** OR
- Bank Name: **"Bank Negara Indonesia"**

### Account Number:
- **Must be exact:** 395351902
- No spaces, no dashes
- Exactly 12 digits for BNI

### Account Holder Name:
- **Exactly as it appears on:** ID card, passport, or bank statement
- **Try:** "ABDUL FAKHRI AL MUBAROK"
- Or: "Abdul Fakhri Al Mubarok" (capitalization matters sometimes)

### Bank Code:
- **Do NOT enter:** 009 (this is for Stripe's internal use only)
- Leave blank if there's a "Bank Code" field
- OR enter: **014** if system asks for routing number

---

## Solution 3: Try Alternative Bank Info Method

### Method A: Use SWIFT Code Instead

If Stripe won't accept account number:

1. Get your BNI SWIFT code
2. Go to: https://dashboard.stripe.com/settings/bank_accounts
3. Click: "Add bank account"
4. Try entering:
   - Bank Name: "Bank Negara Indonesia"
   - SWIFT Code: **BNINDID** (for BNI)
   - Account Number: 395351902

---

## Solution 4: Check If BNI is Actually Supported

### BNI Support Status:
- Stripe DOES support some Indonesian banks
- BNI is generally supported BUT...
- Some Stripe regions have different support

**Try a different bank that's verified to work:**

| Bank | Code | Known to Work? |
|------|------|---|
| BCA (Central Asia) | 014 | ✅ YES |
| Mandiri | 008 | ✅ YES |
| BNI | 009 | ⚠️ SOMETIMES |
| CIMB | 022 | ✅ YES |
| Danamon | 011 | ⚠️ SOMETIMES |

**If BNI doesn't work: Use BCA or Mandiri instead**

---

## Solution 5: Complete Stripe Setup Checklist

Go through EACH step:

### Step 1: Verify Country
- [ ] Go to Settings
- [ ] Check country = **Indonesia** 🇮🇩
- [ ] Save if changed

### Step 2: Enter Correct Info
- [ ] Bank Name: "Bank Negara Indonesia" OR "PT Bank Negara Indonesia (Persero) Tbk"
- [ ] Account Number: 395351902 (no spaces)
- [ ] Account Holder: ABDUL FAKHRI AL MUBAROK
- [ ] Leave bank code blank (or try 009)

### Step 3: Try Adding Account
- [ ] Click "Add bank account"
- [ ] Fill in information carefully
- [ ] Click Save

### Step 4: What Happens Next
- [ ] Stripe sends 2 verification deposits
- [ ] Wait 1-3 business days
- [ ] Check BNI statement
- [ ] Confirm amounts in Stripe

---

## Solution 6: If Still Can't Add - Use Alternative

If Indonesian bank absolutely won't work:

### Option A: Use Alternative Payment Method
1. **PayPal** → Add to Stripe
2. **Wise** → Add to Stripe
3. Connect Indonesian bank to PayPal/Wise instead

### Option B: Use Business Bank Account
- Stripe may require business account for Indonesia
- If you have business account: Try adding that instead

### Option C: Contact Stripe Support
1. Go to: https://dashboard.stripe.com/contact
2. Tell them: "I'm trying to add Indonesian BNI account for payouts"
3. They can help with specific requirements for your region

---

## Quick Diagnostic: What Error Message Do You See?

**Tell me what error Stripe shows when you try to add the account:**

| Error Message | Likely Cause |
|---|---|
| "Invalid account number" | Account number format wrong |
| "Bank not supported" | Indonesia not selected OR bank not supported in your region |
| "Country mismatch" | Account country ≠ Stripe country |
| "Invalid bank details" | Bank name or info format wrong |
| "This payment method is not supported" | Stripe doesn't support Indonesian payouts in your region |

---

## What I Need From You

**To help you fix this, tell me:**

1. **What error message does Stripe show?** (exactly)
2. **What country is your Stripe account set to?** (check Settings)
3. **Have you tried other banks?** (BCA, Mandiri, CIMB)
4. **Is your Stripe account fully verified?** (check for green checkmarks)

---

## Workaround: Accept Payments Without Bank Yet

**If Stripe won't accept Indonesian bank:**

### Option 1: Accept Payments, Handle Payout Later
- Customer pays → Money sits in Stripe
- Add bank account once it works
- Stripe auto-pays to account when verified

### Option 2: Manual Withdrawal Methods
1. **Use Wise/Revolut** → Connect to Stripe
2. **Use PayPal** → Connect to Stripe
3. Then move from PayPal/Wise to Indonesian bank

### Option 3: Ask Stripe Support
- Chat: https://dashboard.stripe.com/contact
- Tell them your situation
- They may whitelist your account

---

## BCA Alternative (If BNI Doesn't Work)

If BNI truly won't work, try **BCA** instead:

```
Bank Name:       Bank Central Asia
Account Number:  (Your BCA account)
Account Holder:  ABDUL FAKHRI AL MUBAROK
Bank Code:       014
```

BCA is most widely supported by Stripe for Indonesia.

---

## Temporary Solution: Use Alternative Payout Method

**Until Indonesian bank works:**

### Use Wise (Recommended)
1. Create Wise account: https://wise.com
2. Add Indonesian BNI there
3. Connect Wise to Stripe
4. Payouts: Stripe → Wise → Your Indonesian bank

### Use PayPal
1. Create PayPal account: https://paypal.com
2. Add Indonesian bank to PayPal
3. Connect PayPal to Stripe
4. Payouts: Stripe → PayPal → Your Indonesian bank

**This adds 1-2 extra steps but WORKS if Stripe won't accept direct.**

---

## Next Steps

**RIGHT NOW:**

1. Tell me: **What error message did you get?**
2. Check: **Is your Stripe country set to Indonesia?**
3. Try: **BCA instead of BNI** (more widely supported)

**THEN:**

I'll give you exact steps to fix it.

---

## Don't Worry

**This is solvable.** Stripe payouts to Indonesia work, but require exact formatting.

Common fixes:
- ✅ Change country to Indonesia
- ✅ Use BCA instead of BNI
- ✅ Use alternative payout (Wise)
- ✅ Contact Stripe support

**You'll get money to your account. Just might need different method.**

