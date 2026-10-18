"""Word lists for masking. All entries are lower case.

KEEP_KEYWORDS and COMMERCE_WORDS are always kept (they describe a transaction, not a person).
NAMES are always masked, even when they are also English words (ROSE, KING, ANAND).
CITIES become [CITY]. Common English words (wordfreq's top list) are kept unless they are names
or cities; see masker.py.
"""

from functools import cache

from wordfreq import top_n_list

COMMON_WORDS_TOP_N = 30000

# Narration structure, payment rails, bank shorthand and words that name a kind of transaction.
KEEP_KEYWORDS = frozenset("""
upi p2a p2m p2p imps neft rtgs nach ach ecs ats atm atw wdl nfs pos bil onl billpay bbps mb mob ib ibl net netbank
impstran imps-tran cwdr wdl dep tfr trf trfr fund funds transfer transferred self own linked sweep autosweep auto debit credit dr cr
to by from for via ref refno txn tran trxn payment pay paid payout payin collect upi_id
mut mutual salary sal payroll wages bonus stipend reimbursement rent emi loan sip mf mutual redemption dividend div interest int
pd int.pd refund reversal rev cashback cash withdrawal deposit chq cheque clg brn branch charges chgs chg fee fees gst
tax tds itns challan cc card credit debit prepaid postpaid recharge bill bills premium policy fd rd maturity
installment instalment insurance mandate tp tpa ecs ach-dr nach-dr nach-cr settlement settle merchant online order
aadhaar aadhar uid pan mob mobile phone ph email mail gst gstin vpa id
of in at on an as is it or co mf cc up no
mr mrs ms shri smt capitalised capitalized quarterly qtrly annual monthly
jan feb mar apr may jun jul aug sep sept oct nov dec january february march april june july august
september october november december
""".split())

# Words that tell what kind of business it is (Indian and English).
COMMERCE_WORDS = frozenset("""
pvt ltd limited llp inc corp co company enterprises enterprise traders trading trader stores store mart supermarket
hypermarket bazaar bazar kirana provision provisions general medicals medical chemist chemists pharmacy pharma
clinic hospital hospitals diagnostics diagnostic labs lab pathlabs nursing healthcare health dental eye optical opticals
bhandar kendra seva sewa mandir temple trust church masjid gurudwara foundation ngo dhaba hotel hotels restaurant
restaurants cafe caffe bakery bakers sweets sweet foods food kitchen canteen mess dairy milk fruits vegetables
salon parlour spa gym fitness academy institute school college university classes coaching tuition education
textiles garments fashion footwear jewellers jewellery jewelers electronics electricals electrical hardware motors
automobiles autos garage service services servicing solutions technologies technology tech software systems
infotech consultancy consultants logistics couriers courier transport transports travels tours cabs taxi
petroleum petrol fuels fuel filling station agencies agency distributors wholesale retail industries
finance finserv capital securities broking stock broking investments investment amc assets asset
municipal corporation nagar palika panchayat govt government department society association apartment apartments
maintenance residency residents welfare housing properties realty builders estate rentals
mobiles mobile telecom communications broadband fiber fibre internet cable dth computers xerox printers stationery
books book toys gifts flowers florist pets pet vet veterinary laundry dry cleaners tailors
insurance assurance life general bank banks payments payment wallet
""".split())

# Banks and UPI handles (the part after @ in a UPI ID).
BANK_WORDS = frozenset("""
sbi sbin hdfc icici icic axis utib kotak kkbk yes yesb idfc idfb pnb punb bob barb canara cnrb union ubin
indian idib indusind indb federal fdrl boi bkid rbl iob uco central citi hsbc dbs sc standard chartered
paytm phonepe gpay googlepay bhim amazonpay cred mobikwik freecharge
okaxis okicici oksbi okhdfcbank ybl ibl axl apl upi waicici waaxis wahdfcbank pingpay ptyes ptaxis pthdfc ptsbi
""".split())

# Indian cities and states (become [CITY]).
CITIES = frozenset("""
mumbai bombay delhi newdelhi noida gurgaon gurugram faridabad ghaziabad bangalore bengaluru chennai madras
hyderabad secunderabad kolkata calcutta pune nashik nagpur aurangabad thane navi solapur kolhapur ahmedabad surat
vadodara baroda rajkot jaipur jodhpur udaipur kota lucknow kanpur varanasi agra allahabad prayagraj meerut patna
ranchi jamshedpur dhanbad bhubaneswar cuttack guwahati shillong durgapur asansol siliguri howrah kochi cochin
ernakulam trivandrum thiruvananthapuram kozhikode calicut thrissur coimbatore madurai trichy tiruchirappalli salem
vellore mysore mysuru mangalore mangaluru hubli dharwad belgaum belagavi visakhapatnam vizag vijayawada guntur
tirupati warangal indore bhopal gwalior jabalpur raipur bilaspur chandigarh mohali ludhiana amritsar jalandhar
dehradun haridwar shimla jammu srinagar goa panaji margao pondicherry puducherry
maharashtra karnataka kerala tamil nadu telangana andhra gujarat rajasthan punjab haryana bihar odisha orissa
bengal assam jharkhand chhattisgarh uttarakhand himachal madhya pradesh uttar
""".split())

# Given names and surnames that are also common English words or otherwise appear in wordfreq's
# top list. Always masked (unless part of a known brand). Indian names first, then Western.
NAMES = frozenset("""
aarav aditya akash amit anand anil anjali ankit anu anupam arjun arun arvind ashok ashish asha deepak dev
devi dinesh divya gaurav geeta gita gopal govind hari harish hema indira jaya jyoti kamal karan kavita kiran
krishna kumar lakshmi lata madhu mahesh manish manoj meena meera mohan mukesh nand neha nikhil nisha nitin
pankaj pooja prakash pramod prem priya rahul raj raja rajesh rajiv raju rakesh ram rama ramesh ravi rekha rohit
sachin sanjay santosh sarita shankar shanti shiva shyam sita sonia sunil sunita suresh sushil uma usha vijay
vikas vikram vinod vishal yash ganesh lalit mohit naveen pradeep rohan sagar sandeep sumit tarun varun
sharma verma gupta singh kumar patel shah mehta joshi rao reddy nair iyer iyengar menon pillai das dutta
datta ghosh bose basu banerjee chatterjee mukherjee mondal mandal sen roy khan ali ahmed hussain sheikh
agarwal aggarwal jain bansal goel garg mittal malhotra kapoor khanna chopra arora bhatia saxena srivastava
mishra pandey tiwari dubey shukla tripathi yadav chauhan rathore thakur naidu chowdhury choudhary desai
kulkarni patil pawar jadhav shinde gaikwad bhat hegde shetty kamath pai fernandes dsouza rodrigues gomes
john james robert michael william david richard joseph thomas charles daniel matthew mark paul steven andrew
kevin brian george edward ronald anthony kenneth jason gary timothy jose larry jeffrey frank scott eric
stephen raymond gregory samuel patrick jack dennis jerry tyler aaron henry adam peter nathan zachary harold
carl arthur gerald roger keith jeremy terry lawrence sean christian albert joe ethan austin jesse willie
billy bruce ralph roy jordan louis philip bobby johnny bill will
mary patricia jennifer linda elizabeth barbara susan jessica sarah karen nancy lisa betty margaret sandra
ashley kimberly emily donna michelle dorothy carol amanda melissa deborah stephanie rebecca sharon laura
cynthia kathleen amy shirley angela helen anna brenda pamela nicole emma samantha katherine christine debra
rachel catherine carolyn janet ruth maria heather diane virginia julie joyce victoria olivia kelly christina
lauren joan evelyn judith megan cheryl andrea hannah martha jacqueline frances gloria ann teresa kathryn
sara janice jean alice madison doris abigail julia judy grace denise amber marilyn beverly danielle theresa
sophia marie diana brittany natalie isabella charlotte rose alexis kayla
rose grace hope joy faith king queen prince sunny lucky happy honey baby rocky angel summer
abdul agnes ajay akbar amir anita babu bharat chandra dey dharma francis gandhi hamid harsh hassan imran jai
kabir kamala kar kareem khalid kohli lal mathew modi mohammad mohammed nikita om pal prasad rai raman rani
rashid sai salim salman samir sana seth shahid shiv tara tariq xavier yusuf zara
syed sayed saiyed md mohd mohamed muhammad sheikh shaikh sk mia pant amman ash hal
""".split())


@cache
def common_words() -> frozenset[str]:
    """wordfreq's most common English words, minus names and places (computed once)."""
    return frozenset(top_n_list("en", COMMON_WORDS_TOP_N)) - NAMES - CITIES
