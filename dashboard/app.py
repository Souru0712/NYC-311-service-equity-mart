from collections import defaultdict

import pandas as pd
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

BACK_TO_TOP = '[↑ Back to top](#top)'

st.set_page_config(
    page_title="NYC 311 Service Equity",
    page_icon="🗽",
    layout="wide",
)

inject_css()

st.markdown('<a name="top"></a>', unsafe_allow_html=True)
st.title("NYC 311 Service Equity Dashboard")
st.markdown("### Does your neighborhood get fair service from the city?")

st.markdown("""
This dashboard investigates whether New York City responds to resident complaints at the same
speed regardless of neighborhood wealth. The short answer — it doesn't always.
""")

# ── Hero stats ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.markdown("""
<div class="hero-stat">
  <div class="number">3M+</div>
  <div class="label">311 requests per year</div>
</div>
""", unsafe_allow_html=True)
col2.markdown("""
<div class="hero-stat">
  <div class="number">2,168</div>
  <div class="label">Census tracts analyzed</div>
</div>
""", unsafe_allow_html=True)
col3.markdown("""
<div class="hero-stat">
  <div class="number">2020–now</div>
  <div class="label">Dataset coverage</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
**On this page:**
[What is 311?](#what-is-311) ·
[The Problem](#the-problem) ·
[What is a Census Tract?](#what-is-a-census-tract) ·
[Key Metrics Explained](#key-metrics-explained) ·
[How to Navigate](#how-to-navigate-this-dashboard) ·
[Data Sources](#data-sources)
""")

st.divider()

# ── What is 311 + Complaint Type Reference ───────────────────────────────────
st.subheader("What is 311?")
st.markdown("""
**311** is New York City's non-emergency government helpline. Residents call or submit requests
online to report problems that need city attention — a broken street light, a rat infestation,
no heat in an apartment in January, a blocked driveway. The city receives over **3 million
requests per year**.

When a request is submitted, it is tagged with a **complaint type** that routes it to the
relevant city agency (NYPD, Health Department, Department of Buildings, etc.). The time between
submission and resolution is the **response time** — the key metric in this dashboard.

Use the table below to understand what each complaint type actually means, which agency handles
it, and what a resident would be reporting. Use the search box to find a specific type.
""")

COMPLAINT_TYPES = {
    "🐀 Pests & Animals": {
        "ANIMAL FACILITY - NO PERMIT": (
            "A facility housing, breeding, or selling animals — such as a pet shop, kennel, "
            "or animal rescue — operating without the required NYC permit. Licensed facilities "
            "must meet health and safety standards for animal care. Health Department or ACC "
            "inspects and can shut down unlicensed operations.",
            "Health/ACC"),
        "ANIMAL IN A PARK": (
            "A wild or stray animal — such as a raccoon, fox, coyote, or injured bird — "
            "found loose in a city park that may be dangerous, injured, or diseased. "
            "Parks Department or Animal Care Centers (ACC) respond to assess and safely "
            "remove or treat the animal.",
            "Parks/ACC"),
        "ANIMAL-ABUSE": (
            "Reports of animals being physically mistreated, neglected, left without food "
            "or water, or kept in unsafe or cruel conditions — including animals left tied "
            "outdoors in extreme weather or confined in vehicles in the heat. "
            "Handled by NYPD and NYC Animal Care Centers; severe cases can result in "
            "criminal charges under New York State animal cruelty laws.",
            "NYPD/ACC"),
        "DEAD ANIMAL": (
            "A deceased animal — typically a rat, bird, raccoon, or stray cat — found on "
            "a public street, sidewalk, or in a park. Sanitation dispatches crews to collect "
            "and dispose of the carcass. Large animals such as deer may require Parks "
            "Department involvement.",
            "Sanitation"),
        "MOSQUITOES": (
            "Standing water or identified mosquito breeding sites in public areas such as "
            "catch basins, vacant lots, or parks. Particularly relevant for West Nile virus "
            "prevention during warm months. The Health Department inspects the location and "
            "applies larvicide to eliminate breeding grounds.",
            "Health"),
        "HARBORING BEES/WASPS": (
            "An active bee hive or wasp nest on public property, in a building, or on "
            "private property visible to neighbors — posing a sting risk to the public. "
            "The Health Department responds to assess whether the hive requires removal "
            "or professional extermination.",
            "Health"),
        "ILLEGAL ANIMAL KEPT AS PET": (
            "A resident keeping an animal that is prohibited as a pet under NYC law — "
            "including ferrets, reptiles over a certain size, wild animals, or livestock. "
            "NYC bans many exotic and wild animals as pets due to public safety and animal "
            "welfare concerns. Health Department or ACC investigates and may confiscate "
            "the animal.",
            "Health/ACC"),
        "ILLEGAL ANIMAL SOLD": (
            "A pet store, breeder, or individual selling animals in violation of NYC law — "
            "including selling prohibited species, selling without required health certificates, "
            "or operating without a license. DCWP and Health Department investigate and "
            "can issue fines or close the operation.",
            "Health/DCWP"),
        "PET SALE": (
            "A complaint about the sale of pets — including a pet store selling sick animals, "
            "selling animals from puppy mills, or violating NYC's retail pet sale regulations. "
            "NYC law restricts the sale of dogs, cats, and rabbits to licensed sources. "
            "DCWP investigates and can issue violations.",
            "DCWP"),
        "POISON IVY": (
            "Poison ivy, poison oak, or other toxic plants found growing in a city park, "
            "playground, or on city-owned property. Contact with these plants causes painful "
            "skin rashes and blistering. The Parks Department dispatches crews to identify "
            "and safely remove the hazard.",
            "Parks"),
        "RODENT": (
            "A rat or mouse sighting on a public street, in a park, near a food establishment, "
            "or inside a residential building. One of the most persistent quality-of-life "
            "issues in NYC. The Health Department inspects the reported location, assesses "
            "burrow activity, and applies bait or works with property owners to eliminate "
            "harborage conditions.",
            "Health"),
        "STANDING WATER": (
            "Pools of stagnant water accumulating on a street, vacant lot, or public space "
            "that do not drain properly. Standing water is a primary breeding ground for "
            "mosquitoes and contributes to West Nile virus risk. DEP investigates drainage "
            "issues; Health Department may apply larvicide.",
            "DEP/Health"),
        "UNSANITARY ANIMAL FACILITY": (
            "A licensed or unlicensed animal facility — shelter, kennel, pet store, or "
            "grooming salon — operating in unsanitary conditions including inadequate waste "
            "removal, overcrowding, or failure to provide clean water and food. Health "
            "Department and ACC inspect and can issue violations or revoke licenses.",
            "Health/ACC"),
        "UNSANITARY ANIMAL PVT PROPERTY": (
            "Animals being kept on private residential property in conditions that create "
            "a public health or nuisance concern — including accumulation of animal waste, "
            "overcrowding, or conditions attracting vermin. Health Department investigates "
            "and can require the owner to remediate conditions or reduce the number of animals.",
            "Health"),
        "UNSANITARY PIGEON CONDITION": (
            "A large congregation of pigeons or active pigeon nesting on a building, bridge, "
            "or public structure creating unsanitary conditions due to excessive droppings. "
            "Pigeon droppings can damage building surfaces and pose a health risk. Health "
            "Department and property owners are expected to implement deterrent measures.",
            "Health"),
    },
    "🌡️ Housing & Building Conditions": {
        "ASBESTOS": (
            "Asbestos-containing materials being disturbed, damaged, or improperly removed "
            "in a building — typically during renovation or demolition work. Disturbed "
            "asbestos releases microscopic fibers that cause mesothelioma and lung cancer. "
            "NYC requires licensed asbestos contractors and DEP permits for any work "
            "disturbing asbestos. DEP investigates and can issue stop-work orders.",
            "DEP"),
        "BOILER": (
            "A malfunctioning, unsafe, or improperly maintained boiler in a residential "
            "building — including a boiler that fails to produce heat or hot water, leaks "
            "steam, or shows signs of carbon monoxide risk. NYC requires annual boiler "
            "inspections. HPD and DOB respond; severe cases may involve FDNY.",
            "HPD/DOB"),
        "BOILERS": (
            "Complaint about building boiler systems — including multiple boilers in a "
            "large residential building that are malfunctioning or inadequately maintained. "
            "Functionally similar to the Boiler complaint type. HPD and DOB respond.",
            "HPD/DOB"),
        "BUILDING CONDITION": (
            "A general unsafe or significantly deteriorated condition in a residential "
            "building that does not fit a more specific category — including crumbling "
            "interior walls, structural cracks, or pervasive deterioration affecting "
            "habitability. HPD inspects and can issue violations or take emergency action.",
            "HPD"),
        "BUILDING DRINKING WATER TANK": (
            "A rooftop water storage tank in a residential or commercial building that "
            "is in disrepair, structurally compromised, or contaminated — posing a risk "
            "to the building's drinking water supply. NYC requires annual inspections and "
            "cleaning of rooftop tanks. DEP and DOB respond.",
            "DEP/DOB"),
        "DOOR/WINDOW": (
            "Broken, damaged, or missing doors, windows, or locks in a residential rental "
            "building that compromise the security or weatherproofing of a unit or common "
            "area. NYC building code requires landlords to maintain all entry points in a "
            "secure and functional condition. HPD inspects and can issue violations requiring "
            "the landlord to make repairs.",
            "HPD"),
        "ELEVATOR": (
            "A broken, malfunctioning, or unsafe elevator in a residential building. "
            "NYC law mandates that buildings over five stories maintain working elevators — "
            "making a non-functional elevator a code violation. HPD inspects and can order "
            "emergency repairs, particularly when elderly or disabled residents are affected.",
            "HPD"),
        "FLOORING/STAIRS": (
            "Broken, rotted, warped, or structurally dangerous floors or stairways inside "
            "a residential building or its common areas. These conditions create serious fall "
            "hazards for residents. HPD classifies severe cases as Class C (immediately "
            "hazardous) violations requiring emergency repair by the landlord.",
            "HPD"),
        "HEAT/HOT WATER": (
            "Tenant has no heat or inadequate heat in their apartment. NYC law requires "
            "landlords to provide heat of at least 68°F between 6 AM and 10 PM when outdoor "
            "temperatures fall below 55°F, and 62°F overnight, from October 1 through May 31. "
            "Hot water (at least 120°F) must be provided 24 hours a day, 365 days a year. "
            "One of the most time-sensitive complaint types — HPD treats heat complaints as "
            "emergencies during heating season.",
            "HPD"),
        "NON-RESIDENTIAL HEAT": (
            "Lack of adequate heat in a non-residential building such as a school, office, "
            "community facility, or place of worship. Different regulations apply than for "
            "residential buildings, but city standards still require minimum temperatures in "
            "occupied commercial spaces. Handled jointly by HPD and DOB depending on the "
            "building type.",
            "HPD/DOB"),
        "OUTSIDE BUILDING": (
            "Unsafe, deteriorating, or non-compliant conditions on the exterior facade of a "
            "building — including crumbling brickwork, spalling concrete, broken railings, "
            "unsecured scaffolding, or exposed wiring. Facade failures can result in falling "
            "debris, posing serious danger to pedestrians. DOB classifies serious facade "
            "defects as hazardous and can mandate emergency protective measures.",
            "HPD/DOB"),
        "PAINT/PLASTER": (
            "Peeling, chipped, or flaking paint or plaster inside a residential unit or "
            "common area. Particularly hazardous in buildings constructed before 1960, where "
            "lead-based paint was commonly used. Lead paint exposure is a serious health risk "
            "especially for children under six. HPD treats lead paint violations as Class C "
            "(immediately hazardous) and can require landlords to remediate within 24 hours.",
            "HPD"),
        "PLUMBING": (
            "Broken, leaking, or non-functional plumbing in a residential rental unit — "
            "including burst or leaking pipes, broken faucets, non-functioning toilets, "
            "backed-up drains, or complete loss of running water. NYC law requires landlords "
            "to maintain all plumbing in working order. Severe cases involving total water "
            "loss or major flooding are treated as emergencies by HPD.",
            "HPD"),
        "UNSANITARY CONDITION": (
            "General unsanitary or unhealthy conditions inside a residential building — "
            "including cockroach or bedbug infestations, rodent evidence, mold, accumulated "
            "garbage in common areas, sewage backups, or vermin other than rats. HPD inspects "
            "and can issue violations requiring landlords to hire pest control services or "
            "address the root cause of the condition.",
            "HPD"),
        "WATER LEAK": (
            "An active water leak from pipes, the ceiling, the roof, or building "
            "infrastructure inside or outside a residential building. Distinct from a "
            "'no water' complaint — water is present but leaking uncontrollably, causing "
            "property damage and potential mold growth. HPD handles building-side leaks; "
            "DEP investigates leaks originating from the city water main.",
            "HPD/DEP"),
        "INDOOR AIR QUALITY": (
            "Poor air quality inside a residential or commercial building — including "
            "chemical fumes from cleaning products or construction, carbon monoxide risk, "
            "mold spores, or inadequate ventilation causing health symptoms. DEP investigates "
            "indoor air quality complaints and can order remediation.",
            "DEP/HPD"),
        "INDOOR SEWAGE": (
            "Raw sewage backing up into a residential unit or building — from floor drains, "
            "toilets, or sinks — due to a blocked or broken sewer line. Indoor sewage "
            "backup is a serious health hazard and treated as an emergency. DEP responds "
            "to city sewer issues; HPD addresses building-side plumbing failures.",
            "DEP/HPD"),
        "LEAD": (
            "Lead hazards inside a residential building — including lead-based paint on "
            "deteriorated surfaces, lead pipes delivering drinking water, or lead dust "
            "generated by construction or renovation. Lead exposure causes irreversible "
            "neurological damage especially in children under six. HPD treats lead "
            "violations as Class C (immediately hazardous) emergencies.",
            "HPD"),
        "MOLD": (
            "Visible mold growth in a residential unit or building common area — typically "
            "caused by chronic moisture, water leaks, or inadequate ventilation. Mold "
            "exposure can trigger respiratory problems and allergic reactions. HPD inspects "
            "and can issue violations requiring landlords to remediate both the mold and "
            "its underlying moisture source.",
            "HPD"),
        "UNSTABLE BUILDING": (
            "A building showing signs of structural instability — including visible leaning, "
            "large cracks in load-bearing walls, a foundation shift, or conditions suggesting "
            "imminent partial or total collapse. DOB Emergency Response Team responds "
            "immediately; FDNY and NYPD are typically co-dispatched. Call 911 if collapse "
            "appears imminent.",
            "DOB/FDNY"),
        "WATER SYSTEM": (
            "No water supply, discolored or foul-smelling water, very low water pressure, "
            "or intermittent water service in a residential building. Causes can include a "
            "broken building pipe, city main break, or landlord failure to pay the water bill. "
            "HPD handles building-side issues; DEP investigates problems with the city's "
            "water distribution infrastructure.",
            "HPD/DEP"),
        "WINDOW GUARD": (
            "Missing, broken, or improperly installed window guards in an apartment where "
            "children under 10 live or regularly spend time. NYC law requires landlords to "
            "install approved window guards in these units upon tenant request and in all "
            "apartments in buildings where the landlord knows a child under 10 resides. "
            "Failure to install window guards is a Class C violation. HPD inspects.",
            "HPD"),
    },
    "🍽️ Food, Health & Consumer": {
        "BEACH/POOL/SAUNA COMPLAINT": (
            "Unsafe, unsanitary, or non-compliant conditions at a city-operated public beach, "
            "swimming pool, or sauna — including inadequate water quality, lack of lifeguards, "
            "broken facilities, or health code violations. Health Department and Parks "
            "Department inspect and can temporarily close facilities posing health risks.",
            "Health/Parks"),
        "BOTTLED WATER": (
            "A request for bottled water distribution — typically during a water service "
            "outage, contamination event, or emergency where tap water is unavailable or "
            "unsafe. DEP coordinates emergency water distribution through OEM during "
            "declared emergencies.",
            "DEP/OEM"),
        "CALORIE LABELING": (
            "A food service establishment not displaying required calorie information on "
            "its menu. NYC law requires chain restaurants with 15 or more locations nationwide "
            "to post calorie counts prominently on menus and menu boards. Health Department "
            "inspects and can issue violations.",
            "Health"),
        "CANNABIS RETAILER": (
            "A cannabis retailer operating without a required state license, selling to "
            "minors, operating in a prohibited location, or otherwise violating NYS Cannabis "
            "Law. NYC's Sheriff's Office and SLA (State Liquor Authority) coordinate "
            "enforcement of unlicensed cannabis retail operations.",
            "NYPD/Sheriff"),
        "AIR QUALITY": (
            "Complaints about outdoor air quality — including visible smoke, dust, chemical "
            "fumes, strong industrial odors, or emissions from construction equipment, diesel "
            "trucks, or manufacturing facilities. DEP investigates potential violations of "
            "NYC air quality standards and can issue fines to polluters.",
            "DEP"),
        "CONSUMER COMPLAINT": (
            "A complaint about a business engaging in deceptive, unfair, or illegal "
            "commercial practices — including false advertising, price gouging, "
            "bait-and-switch tactics, unlicensed operation, or non-delivery of paid goods "
            "and services. Handled by the NYC Department of Consumer and Worker Protection "
            "(DCWP), which can investigate, mediate disputes, and impose fines.",
            "DCWP"),
        "DRINKING": (
            "Consumption of alcohol in a public space where it is prohibited — such as a "
            "park, playground, beach, street corner, or subway platform. Public drinking is "
            "a violation of NYC Administrative Code. NYPD officers can issue summonses or "
            "make arrests depending on behavior and context.",
            "NYPD"),
        "DRINKING WATER": (
            "Concerns about the quality, taste, color, or odor of tap water from a public "
            "source — distinct from a building-level water system complaint. May involve "
            "discolored water from a main break, chlorine taste, or suspected contamination. "
            "DEP investigates and can issue public advisories if a systemic issue is found.",
            "DEP"),
        "FACE COVERING VIOLATION": (
            "A business or individual violating COVID-19 face mask or face covering "
            "requirements during the pandemic period. This complaint type was active during "
            "2020–2022 when NYC mandated face coverings in public spaces and businesses. "
            "Historical data for this type reflects the pandemic enforcement period.",
            "NYPD/Health"),
        "FOAM BAN ENFORCEMENT": (
            "A food service establishment using banned polystyrene foam (Styrofoam) "
            "containers, cups, or trays. NYC banned single-use expanded polystyrene food "
            "service items in 2019. DSNY and DCWP enforce the ban; repeat violations can "
            "result in substantial fines.",
            "DSNY/DCWP"),
        "FOOD ESTABLISHMENT": (
            "Unsanitary or unsafe conditions inside a licensed food service business — "
            "restaurant, café, food truck, bakery, deli, or catering facility. Includes "
            "pest sightings, improper food storage temperatures, employee hygiene violations, "
            "unclean preparation surfaces, or missing permits. The Health Department inspects "
            "and can issue violations, mandate temporary closures, or revoke operating "
            "permits. Not for food quality or bad service — those are not Health violations.",
            "Health"),
        "FOOD POISONING": (
            "Suspected foodborne illness linked to a specific restaurant, food cart, or "
            "food establishment. Symptoms reported typically include nausea, vomiting, "
            "diarrhea, or fever shortly after eating at the location. Health Department "
            "investigates and can conduct an unannounced inspection; clusters of reports "
            "from the same establishment can trigger a closure.",
            "Health"),
        "MOBILE FOOD VENDOR": (
            "A complaint about a street food cart or food truck operating without required "
            "permits, blocking a public sidewalk or bus stop, handling food in an unsanitary "
            "manner, or operating outside their licensed location or hours. Handled jointly "
            "by the Health Department (food safety) and DCWP (licensing and location "
            "compliance).",
            "Health/DCWP"),
        "NONCOMPLIANCE WITH PHASED REOPENING": (
            "A business violating NYC's COVID-19 phased reopening rules — operating beyond "
            "permitted capacity, ignoring social distancing requirements, or opening before "
            "its sector was permitted to reopen. Active during 2020–2021. Historical data "
            "reflects pandemic-era enforcement.",
            "NYPD/Health"),
        "OUTDOOR DINING": (
            "A complaint about a restaurant's outdoor dining setup — including tables "
            "blocking sidewalk access, noise from outdoor diners, a structure that exceeds "
            "permitted dimensions, or safety concerns with outdoor dining furniture or "
            "barriers. DOT and DCA regulate outdoor dining permits.",
            "DOT/DCA"),
        "PRIVATE OR CHARTER SCHOOL REOPENING": (
            "A private or charter school reopening for in-person instruction in violation "
            "of COVID-19 health and safety protocols. Active during the 2020–2021 school "
            "year. Historical data reflects pandemic-era enforcement.",
            "Health/DOE"),
        "PRIVATE SCHOOL VACCINE MANDATE NON-COMPLIANCE": (
            "A private school not complying with NYC or NYS vaccine mandate requirements "
            "for students or staff — including failure to verify vaccination status or "
            "grant exemptions properly. Health Department investigates.",
            "Health"),
        "RADIOACTIVE MATERIAL": (
            "Suspected improper handling, storage, transportation, or disposal of "
            "radioactive materials or radiation-emitting equipment. DEP's radiation "
            "protection program investigates; the NRC (Nuclear Regulatory Commission) "
            "may be involved for federally licensed materials.",
            "DEP"),
        "RETAILER COMPLAINT": (
            "A complaint about a retail store's business practices, conditions, or "
            "compliance — including selling age-restricted products to minors, deceptive "
            "pricing, or violation of consumer protection laws. DCWP investigates and "
            "can issue fines or suspend licenses.",
            "DCWP"),
        "SMOKING OR VAPING": (
            "Smoking cigarettes, cigars, or marijuana, or using e-cigarettes and vaping "
            "devices in a prohibited area — including city parks, playgrounds, beaches, "
            "public plazas, building entrances, restaurants, and bars. NYC's Smoke-Free "
            "Air Act is among the strictest in the country. Violations are handled by "
            "Health Department enforcement or NYPD.",
            "Health/NYPD"),
        "TANNING": (
            "An unlicensed or unsafe tanning salon or UV tanning bed operation. NYC "
            "requires tanning salons to be licensed and to comply with safety regulations "
            "including age restrictions (no tanning for minors), mandatory warning disclosures, "
            "and equipment maintenance standards. Health Department inspects and can close "
            "non-compliant facilities.",
            "Health"),
        "TATTOOING": (
            "An unlicensed or unsanitary tattooing or body piercing operation. NYC requires "
            "tattoo artists to be licensed by the Health Department and to maintain sterile "
            "conditions and single-use needles to prevent bloodborne disease transmission "
            "including hepatitis and HIV. The Health Department can close unlicensed "
            "operations and issue fines.",
            "Health"),
        "TRANS FAT": (
            "A restaurant or food service establishment using artificial trans fats "
            "(partially hydrogenated oils) in food preparation or service. NYC banned "
            "artificial trans fats in restaurant cooking in 2008 — one of the first such "
            "bans in the world. Health Department inspects and can issue violations.",
            "Health"),
        "VACCINE MANDATE NON-COMPLIANCE": (
            "A business, employer, or organization not complying with NYC COVID-19 "
            "vaccine mandate requirements — including failure to verify employee or "
            "customer vaccination status. Active during 2021–2022. Health Department "
            "and Sheriff's Office investigated complaints.",
            "Health"),
        "WATER QUALITY": (
            "Concerns about the taste, smell, color, or safety of tap water from the "
            "city's water distribution system — including brownish or cloudy water, "
            "unusual odors, or suspected chemical contamination not linked to a specific "
            "building. DEP investigates and can issue public boil-water advisories if "
            "contamination is confirmed.",
            "DEP"),
        "WATER CONSERVATION": (
            "Illegal or wasteful use of city water — including illegally opened fire hydrants, "
            "broken or unattended sprinkler systems, illegal connections tapping city water "
            "mains, or commercial operations violating water use rules. Illegal hydrant "
            "opening is particularly serious as it reduces water pressure available for "
            "firefighting. DEP investigates and can issue substantial fines.",
            "DEP"),
        "X-RAY MACHINE/EQUIPMENT": (
            "Improperly operated or maintained X-ray equipment in a medical, dental, "
            "veterinary, or other facility — including equipment without proper radiation "
            "shielding, operated by unlicensed personnel, or in a facility lacking the "
            "required DEP permit. DEP's radiation control program inspects and can "
            "order equipment taken out of service.",
            "DEP"),
    },
    "🔊 Noise": {
        "COLLECTION TRUCK NOISE": (
            "Excessive noise from a NYC Sanitation collection truck during overnight or "
            "early morning pickup hours — including loud hydraulic compactors, banging "
            "metal containers, or idling engines near residential buildings. NYC Noise Code "
            "limits sanitation operations noise. Sanitation investigates and can adjust "
            "routes or equipment.",
            "Sanitation"),
        "ILLEGAL FIREWORKS": (
            "Consumer fireworks being set off illegally — outside of permitted July 4th "
            "events, in residential areas, or by unlicensed individuals. Illegal fireworks "
            "are a significant fire hazard and can cause serious injuries including burns "
            "and loss of fingers. NYPD and FDNY respond; possession of illegal fireworks "
            "carries substantial fines and potential arrest.",
            "NYPD/FDNY"),
        "NOISE": (
            "A general noise disturbance that does not fit a more specific subcategory — "
            "such as noise from construction equipment outside permitted hours, amplified "
            "sound from an unidentified source, or a mix of noise types. Used when the "
            "source is unclear or does not match the more specific noise categories. "
            "NYPD responds.",
            "NYPD"),
        "NOISE - HELICOPTER": (
            "Excessive, low-altitude, or repetitive helicopter noise over a residential "
            "neighborhood from private, commercial, or tourism helicopter flights. "
            "NYC has one of the highest concentrations of helicopter traffic in the country. "
            "FAA regulates airspace; NYC coordinates with the FAA and operators on noise "
            "abatement procedures for tour and charter flights.",
            "FAA/NYC"),
        "NOISE - COMMERCIAL": (
            "Excessive noise originating from a commercial business — including loud music "
            "from a bar, restaurant, nightclub, or retail store; noisy HVAC or refrigeration "
            "equipment on a building exterior; or delivery trucks loading at prohibited hours. "
            "NYC Noise Code sets specific decibel limits for commercial establishments. "
            "NYPD can issue summonses.",
            "NYPD"),
        "NOISE - HOUSE OF WORSHIP": (
            "Excessive amplified sound — music, announcements, or services broadcast through "
            "outdoor loudspeakers — from a church, mosque, temple, synagogue, or other "
            "religious venue. NYC Noise Code applies equally to houses of worship. NYPD "
            "responds; resolutions often involve negotiated volume reduction.",
            "NYPD"),
        "NOISE - PARK": (
            "Noise originating from within or directly adjacent to a city park — including "
            "amplified music, loud gatherings, unpermitted events, or commercial activity. "
            "Parks Enforcement Patrol (PEP) and NYPD can respond depending on the nature "
            "and severity of the disturbance.",
            "Parks/NYPD"),
        "NOISE - RESIDENTIAL": (
            "Excessive noise coming from inside a residential building — including loud music, "
            "television, parties, dogs barking persistently, or stomping and impact noise "
            "from neighbors above. The most common noise complaint type citywide. NYC Noise "
            "Code requires residential noise to stay below 45 decibels between 10 PM and "
            "7 AM. NYPD responds.",
            "NYPD"),
        "NOISE - STREET/SIDEWALK": (
            "Noise generated by people on a public street or sidewalk — including loud "
            "conversations, crowds gathered outside bars or clubs, unpermitted street "
            "performers, or groups congregating late at night. NYPD responds and can "
            "disperse gatherings or issue noise violations.",
            "NYPD"),
        "NOISE - VEHICLE": (
            "Noise from a car, truck, or motorcycle on a public street — including a car "
            "alarm sounding for an extended period, an engine being repeatedly revved, a "
            "modified or illegally loud exhaust system, or loud music from a vehicle's "
            "sound system. NYPD can issue summonses for noise code violations.",
            "NYPD"),
    },
    "🚗 Streets & Vehicles": {
        "BIKE RACK": (
            "A request for a new bike rack to be installed at a location lacking secure "
            "bicycle parking, or a complaint that an existing rack is in the wrong location. "
            "DOT manages the city's bike rack installation program and prioritizes locations "
            "with high bicycle traffic.",
            "DOT"),
        "BIKE RACK CONDITION": (
            "An existing bike rack that is damaged, bent, or missing — making it unusable "
            "for secure bicycle parking. DOT repairs or replaces damaged racks.",
            "DOT"),
        "BIKE/ROLLER/SKATE CHRONIC": (
            "A recurring, persistent pattern of cyclists, skaters, or skateboarders "
            "riding unsafely or in prohibited areas at a specific location — despite "
            "previous enforcement. NYPD may deploy targeted enforcement at identified "
            "chronic locations.",
            "NYPD"),
        "BRIDGE CONDITION": (
            "Structural damage, deterioration, or safety concerns on a city-owned bridge — "
            "including cracked or spalling concrete, failing expansion joints, damaged "
            "railings, or road surface defects on the bridge deck. DOT's Bridge Division "
            "inspects and prioritizes repairs based on structural urgency.",
            "DOT"),
        "BROKEN PARKING METER": (
            "A parking meter that is damaged, jammed, not accepting payment, displaying "
            "incorrectly, or otherwise non-functional. DOT manages the city's parking meter "
            "network and dispatches repair crews. A broken meter does not excuse illegal "
            "parking — the posted time limit still applies.",
            "DOT"),
        "ABANDONED BIKE": (
            "A bicycle left locked or unlocked on public property — a street sign, fence, "
            "or rack — for an extended period with no signs of use, or with a flat tire, "
            "rust, or missing parts indicating it has been abandoned. Sanitation removes "
            "abandoned bikes after tagging them with a removal notice.",
            "Sanitation"),
        "ABANDONED VEHICLE": (
            "A car, truck, van, or motorcycle left on a public street for more than 72 hours "
            "without being moved, with expired registration, or showing signs of being "
            "stripped, damaged, or permanently inoperable. NYPD and Sanitation coordinate "
            "to tag and tow the vehicle.",
            "NYPD/Sanitation"),
        "BIKE/ROLLER/SKATE": (
            "Cyclists, in-line skaters, or skateboarders riding unsafely or in areas where "
            "it is prohibited — including on sidewalks, in pedestrian plazas, in parks with "
            "no-cycling rules, or through red lights in a dangerous manner. NYPD can issue "
            "moving violations or summonses.",
            "NYPD"),
        "BLOCKED DRIVEWAY": (
            "A vehicle is illegally parked in front of a private driveway, preventing the "
            "property owner from entering or exiting. One of the most common NYPD parking "
            "complaints in NYC. Officers can issue a summons and arrange towing if the "
            "vehicle owner cannot be located promptly.",
            "NYPD"),
        "CURB CONDITION": (
            "A damaged, missing, or non-compliant curb cut or curb edge — particularly "
            "those affecting wheelchair and mobility device accessibility at crosswalks. "
            "The Americans with Disabilities Act (ADA) requires accessible curb cuts at all "
            "intersections. DOT repairs damaged curbs and installs missing cuts.",
            "DOT"),
        "DEP HIGHWAY CONDITION": (
            "A road surface defect or damage on a highway or road managed by DEP — "
            "typically near DEP infrastructure such as water mains, sewer lines, or "
            "treatment plants. DEP coordinates repairs on roadways adjacent to its "
            "own infrastructure.",
            "DEP"),
        "DEP SIDEWALK CONDITION": (
            "A sidewalk defect on DEP-managed property — such as near a water treatment "
            "facility, reservoir, or other DEP installation. DEP is responsible for "
            "maintaining sidewalks adjacent to its own properties.",
            "DEP"),
        "DEP STREET CONDITION": (
            "A street surface defect on a DEP-managed roadway — typically access roads "
            "or streets adjacent to DEP water or sewer infrastructure. DEP repairs road "
            "damage caused by its own construction or infrastructure.",
            "DEP"),
        "DERELICT BICYCLE": (
            "A bicycle in severely deteriorated condition — rusted, missing wheels, or "
            "structurally unusable — left attached to public property for an extended "
            "period. Distinct from an abandoned bike in that the bicycle is clearly beyond "
            "use. Sanitation removes derelict bicycles after tagging.",
            "Sanitation"),
        "DERELICT VEHICLES": (
            "Multiple abandoned or junked vehicles on a public street, vacant lot, or "
            "private property visible from the street — particularly stripped, burned, or "
            "partially dismantled cars. Often associated with illegal chop shop activity. "
            "NYPD and Sanitation coordinate removal; multiple vehicles may trigger an "
            "investigation.",
            "NYPD/Sanitation"),
        "E-SCOOTER": (
            "A complaint about an electric scooter illegally parked, blocking a sidewalk, "
            "or ridden unsafely — including on sidewalks where prohibited or at excessive "
            "speed. NYC operates licensed e-scooter share programs in select boroughs; "
            "unlicensed and private e-scooters face additional restrictions. NYPD enforces "
            "e-scooter regulations.",
            "NYPD"),
        "HIGHWAY CONDITION": (
            "Damage or safety hazards on a city-managed highway — including potholes, "
            "cracked pavement, damaged barriers, or debris in travel lanes. DOT's highway "
            "division responds; major state highways may involve NYSDOT.",
            "DOT"),
        "HIGHWAY SIGN - DAMAGED": (
            "A directional, informational, or regulatory highway sign that has been "
            "damaged by a vehicle collision, weather, or vandalism and is no longer fully "
            "legible or properly positioned. DOT replaces or repairs damaged highway signs.",
            "DOT"),
        "HIGHWAY SIGN - DANGLING": (
            "A highway sign that is partially detached from its post or overhead structure "
            "and hanging loosely — posing a falling hazard to vehicles below. DOT treats "
            "dangling signs as urgent safety hazards requiring immediate response.",
            "DOT"),
        "MUNICIPAL PARKING FACILITY": (
            "A complaint about conditions in a city-owned or operated parking facility — "
            "including structural damage, inadequate lighting, broken equipment, or "
            "safety concerns. NYC's Department of Transportation manages municipal "
            "parking facilities.",
            "DOT"),
        "ROOT/SEWER/SIDEWALK CONDITION": (
            "Tree roots from a city street tree that have grown into and damaged sewer "
            "lines or uplifted adjacent sidewalk panels — causing both infrastructure "
            "damage and a tripping hazard. Requires coordination between Parks (tree), "
            "DEP (sewer), and DOT (sidewalk) for a comprehensive repair.",
            "Parks/DEP/DOT"),
        "SQUEEGEE": (
            "Individuals aggressively washing car windshields at intersections or in "
            "traffic without being asked — and then demanding payment. Squeegee activity "
            "at intersections can slow traffic and create confrontational situations. "
            "NYPD responds and can issue summonses.",
            "NYPD"),
        "STREET LIGHT CONDITION": (
            "A streetlight that is out, flickering, staying on during daylight hours, "
            "or has been damaged by a vehicle or weather. Broken streetlights reduce "
            "pedestrian safety at night and can contribute to crime. DOT manages the city's "
            "streetlight network and dispatches repair crews.",
            "DOT"),
        "STREET SIGN - DANGLING": (
            "A street name or regulatory sign that is partially attached and hanging "
            "dangerously from its post — posing a falling hazard and creating confusion "
            "for drivers. DOT treats dangling signs as priority repairs.",
            "DOT"),
        "TUNNEL CONDITION": (
            "Structural damage, drainage problems, lighting failures, or safety hazards "
            "inside a city-managed road tunnel. DOT manages NYC's road tunnels; MTA "
            "oversees subway tunnels. Serious structural issues in tunnels are treated as "
            "emergencies.",
            "DOT"),
        "ILLEGAL PARKING": (
            "A vehicle parked in violation of NYC parking rules — including blocking a fire "
            "hydrant (within 15 feet), parking in a crosswalk or bus stop, double parking, "
            "parking on a sidewalk, blocking a bike lane, or parking during street cleaning "
            "hours. NYPD traffic enforcement can issue summonses and arrange towing for "
            "serious violations.",
            "NYPD/DOT"),
        "OBSTRUCTION": (
            "Something blocking a public sidewalk, street, or building entrance in a way "
            "that impedes pedestrian or vehicle access — including scaffolding erected "
            "without a permit, a dumpster placed in the roadway, construction debris on "
            "the sidewalk, or store merchandise extending onto the public right of way. "
            "DOT and DOB respond depending on whether construction activity is involved.",
            "DOT/DOB"),
        "SIDEWALK CONDITION": (
            "A broken, cracked, uneven, uplifted, or otherwise dangerous sidewalk surface. "
            "In NYC, property owners — not the city — are generally responsible for "
            "maintaining the sidewalk adjacent to their building. DOT administers the "
            "Sidewalk Repair Program and can order owners to make repairs; serious hazards "
            "may be repaired by the city with costs billed back to the owner.",
            "DOT"),
        "STREET CONDITION": (
            "A pothole, crack, sunken pavement, raised utility cover, or other hazardous "
            "surface defect in the roadway. DOT is responsible for maintaining city streets "
            "and prioritizes large or dangerous potholes for rapid repair. Unreported "
            "potholes that cause vehicle damage can result in city liability claims.",
            "DOT"),
        "STREET SIGN - DAMAGED": (
            "A street name sign, regulatory sign (stop, yield, one-way), or warning sign "
            "that has been bent, knocked over, vandalized, faded beyond readability, or "
            "otherwise damaged. Missing or unreadable signs create traffic hazards and can "
            "impair emergency response navigation. DOT crews repair or replace damaged signs.",
            "DOT"),
        "STREET SIGN - MISSING": (
            "A street name sign, stop sign, yield sign, or other regulatory sign that has "
            "been completely removed, stolen, or destroyed. Missing traffic control signs "
            "can contribute to accidents at intersections. DOT prioritizes replacement of "
            "missing stop signs and other critical safety signs.",
            "DOT"),
        "TRAFFIC": (
            "A general traffic-related issue not covered by other specific categories — "
            "such as a dangerous intersection lacking adequate signage, a confusing road "
            "layout, a missing lane marking, or a recurring bottleneck caused by an "
            "infrastructure problem. DOT and NYPD evaluate and may implement engineering "
            "solutions or enforcement measures.",
            "DOT/NYPD"),
        "TRAFFIC SIGNAL CONDITION": (
            "A traffic light that is dark (completely non-functional), flashing when it "
            "should be cycling normally, showing conflicting signals simultaneously, or "
            "has been knocked out of alignment by a vehicle collision. A non-functioning "
            "traffic signal is a serious safety hazard. DOT Emergency Response units "
            "prioritize repairs at busy intersections.",
            "DOT"),
    },
    "🗑️ Sanitation & Environment": {
        "CHANGE COLLECTION SCHEDULE": (
            "A request to modify the garbage, recycling, or organics collection schedule "
            "for a specific address or block — such as requesting a different pickup day "
            "or adjusting frequency. NYC Sanitation evaluates requests based on route "
            "logistics and community need.",
            "Sanitation"),
        "COMMERCIAL DISPOSAL COMPLAINT": (
            "A business illegally disposing of commercial waste — placing garbage in "
            "residential bins to avoid sanitation fees, dumping waste on the street outside "
            "permitted pickup windows, using improper containers, or contracting with "
            "unlicensed carters. NYC requires all commercial businesses to use licensed "
            "private carters. Sanitation investigates and can issue substantial fines.",
            "Sanitation"),
        "DAMAGED TREE": (
            "A city-owned street tree that has been damaged by a vehicle collision, "
            "severe storm, vandalism, or construction activity — but is not yet dead or "
            "dying. Parks Department arborists assess the damage and determine whether "
            "the tree can be saved with treatment or requires removal.",
            "Parks"),
        "DEAD/DYING TREE": (
            "A city-owned street tree — a tree planted in a sidewalk tree pit — that "
            "appears dead, dying, structurally compromised, or at risk of falling. Dead or "
            "severely weakened trees can topple in storms, causing property damage and "
            "serious injury. Parks Department arborists assess and schedule removal or "
            "treatment.",
            "Parks"),
        "DIRTY CONDITIONS": (
            "Accumulated garbage, litter, or debris on a public street, sidewalk, or lot — "
            "functionally identical to the Dirty Condition complaint type. Both categories "
            "route to NYC Sanitation for investigation and cleanup.",
            "Sanitation"),
        "DIRTY CONDITION": (
            "Garbage, litter, illegally dumped bags, or debris accumulating on a public "
            "street, sidewalk, alley, or vacant lot. The most common sanitation complaint "
            "citywide. NYC Sanitation can issue violations to property owners responsible "
            "for the adjacent sidewalk. Chronic dirty conditions may indicate a need for "
            "increased collection frequency in that area.",
            "Sanitation"),
        "DSNY SPILLAGE": (
            "Garbage, liquid, or other material spilled by a NYC Sanitation vehicle or "
            "during a collection operation — left on the street or sidewalk. Sanitation "
            "is required to clean up after its own operations. Complaints trigger a "
            "cleanup crew dispatch.",
            "Sanitation"),
        "DUMPSTER COMPLAINT": (
            "A dumpster that is improperly placed on a public street or sidewalk without "
            "a permit, overflowing with waste, creating an odor, blocking pedestrian or "
            "vehicle access, or being used for unauthorized dumping. DOT manages dumpster "
            "placement permits; Sanitation handles waste overflow issues.",
            "DOT/Sanitation"),
        "ELECTRONICS WASTE": (
            "Improper disposal of electronic equipment — televisions, computers, monitors, "
            "or other e-waste — placed on the curb outside of scheduled e-waste collection "
            "events or drop-off programs. NYC prohibits e-waste in regular trash. Sanitation "
            "enforces e-waste disposal rules.",
            "Sanitation"),
        "ELECTRONICS WASTE APPOINTMENT": (
            "A request to schedule a pickup appointment for electronic waste items — "
            "such as old TVs or computers — that cannot go in regular garbage. NYC Sanitation "
            "provides scheduled e-waste collection through its SAFE disposal program.",
            "Sanitation"),
        "GRAFFITI": (
            "Vandalism graffiti spray-painted, drawn, or scratched onto a public surface, "
            "building facade, subway structure, park bench, or other city property. The "
            "Sanitation Department removes graffiti from public property. Property owners "
            "are responsible for removing graffiti from their private buildings. Chronic "
            "graffiti in an area can indicate a need for targeted anti-vandalism efforts.",
            "Sanitation/Parks"),
        "HAZARDOUS MATERIALS": (
            "Improper storage, handling, or disposal of hazardous chemicals — including "
            "industrial solvents, cleaning agents, paints, batteries, or other toxic "
            "materials found in a public space or improperly discarded. DEP and FDNY's "
            "Hazmat Unit respond to assess and safely contain or remove the materials.",
            "DEP/FDNY"),
        "ILLEGAL POSTING": (
            "Unauthorized flyers, posters, stickers, or advertisements affixed to public "
            "property — including utility poles, traffic signs, bus shelters, and city "
            "buildings. Illegal posting is prohibited under NYC Administrative Code. "
            "Sanitation and DOT remove illegal postings and can fine those responsible.",
            "Sanitation/DOT"),
        "INDUSTRIAL WASTE": (
            "Improper disposal of waste generated by industrial or manufacturing operations "
            "— including factory byproducts, chemical waste, or production scraps dumped "
            "in public spaces or mixed with regular trash. Sanitation and DEP investigate; "
            "violations can result in substantial fines.",
            "Sanitation/DEP"),
        "INSTITUTION DISPOSAL COMPLAINT": (
            "A hospital, school, religious institution, or other large non-commercial "
            "institution improperly disposing of waste — using residential bins, dumping "
            "on the street, or contracting with unlicensed carters. NYC requires institutions "
            "to use licensed commercial waste haulers. Sanitation investigates.",
            "Sanitation"),
        "ILLEGAL DUMPING": (
            "Someone illegally dumping bulk waste in a public space — including construction "
            "debris, old furniture, appliances, bags of household garbage, or hazardous "
            "materials — in a vacant lot, alley, street corner, or park. A serious offense "
            "in NYC with fines up to $10,000 for repeat offenders. Sanitation investigates "
            "and may install surveillance cameras in chronic dumping locations.",
            "Sanitation"),
        "ILLEGAL TREE DAMAGE": (
            "A city-owned street tree that has been cut down, pruned, or damaged without a "
            "permit from the Parks Department. NYC street trees are city property — "
            "unauthorized removal or significant pruning is a violation of NYC Administrative "
            "Code and can result in fines and mandatory replacement costs at the violator's "
            "expense. Street trees provide stormwater management, urban cooling, and air "
            "quality benefits.",
            "Parks"),
        "LOT CONDITION": (
            "An overgrown, unsanitary, hazardous, or improperly maintained vacant lot — "
            "including high weeds, accumulated debris, open access that attracts dumping, "
            "or standing water. Property owners are responsible for maintaining vacant "
            "lots. Sanitation and HPD can issue violations requiring cleanup.",
            "Sanitation/HPD"),
        "LITTER BASKET / REQUEST": (
            "A combined complaint about a litter basket condition or a request for a new "
            "one — used when the 311 filing covers both the need for a basket and an issue "
            "with an existing one nearby. Sanitation routes the complaint to the appropriate "
            "response unit.",
            "Sanitation"),
        "LITTER BASKET COMPLAINT": (
            "A public trash can — on a street corner, in a park, or at a bus stop — that "
            "is overflowing, damaged, has been set on fire, or is otherwise not functioning. "
            "Overflowing baskets contribute to dirty conditions and attract rats. Sanitation "
            "services the basket and may adjust the collection schedule for that location.",
            "Sanitation"),
        "LITTER BASKET REQUEST": (
            "A request for a new public trash can to be installed at a location that "
            "currently has none or has insufficient capacity for its foot traffic. Sanitation "
            "evaluates the location based on pedestrian volume and installs baskets where "
            "demand justifies them.",
            "Sanitation"),
        "MISSED COLLECTION (ALL MATERIALS)": (
            "All types of material — garbage, recycling, and organics — that were properly "
            "prepared and placed out for collection but were not picked up on the scheduled "
            "day. Filed when the entire collection was missed rather than a single material "
            "stream. Sanitation arranges a return collection.",
            "Sanitation"),
        "MISSED COLLECTION": (
            "Garbage, recycling, or organic/compost material that was properly prepared and "
            "placed out for scheduled collection but was not picked up on the assigned day. "
            "NYC Sanitation has specific rules for when and how materials must be placed out. "
            "A missed pickup may result from a scheduling issue or improper preparation. "
            "Sanitation investigates and arranges a return collection.",
            "Sanitation"),
        "NEW TREE REQUEST": (
            "A request for the NYC Parks Department to plant a new street tree at a "
            "specific location — typically an empty tree pit or a block with no existing "
            "street trees. Parks evaluates requests based on available space, soil "
            "conditions, and planting priorities.",
            "Parks"),
        "OIL OR GAS SPILL": (
            "A spill of oil, gasoline, diesel, or other petroleum product on a street, "
            "in a waterway, or on public land. Even small fuel spills can contaminate "
            "storm drains and waterways. DEP and FDNY Hazmat respond; large spills may "
            "involve the Coast Guard if near water.",
            "DEP/FDNY"),
        "OVERFLOWING LITTER BASKETS": (
            "Public litter baskets on streets or in parks that are overflowing with "
            "garbage — creating unsanitary conditions and attracting rats. Similar to "
            "the Litter Basket Complaint type. Sanitation dispatches crews to empty "
            "baskets and may increase collection frequency.",
            "Sanitation"),
        "OVERFLOWING RECYCLING BASKETS": (
            "Public recycling containers that are overflowing — typically in parks, "
            "plazas, or street corners. Sanitation empties the containers and may "
            "increase service frequency for high-volume locations.",
            "Sanitation"),
        "OVERGROWN TREE/BRANCHES": (
            "Branches from a city-owned street tree that are hanging too low over the street "
            "or sidewalk, blocking traffic signs, obstructing streetlights, interfering with "
            "power lines, or encroaching on a building. Parks Department arborists assess "
            "and prune branches as needed. Branches contacting power lines require "
            "coordination with Con Edison.",
            "Parks"),
        "POSTING ADVERTISEMENT": (
            "Unauthorized commercial advertisements — flyers, stickers, or signs — "
            "affixed to public property including utility poles, traffic signs, fences, "
            "or city infrastructure. Similar to Illegal Posting but specifically for "
            "commercial advertising. Sanitation removes and can issue fines to the "
            "businesses or individuals responsible.",
            "Sanitation"),
        "RECYCLING BASKET COMPLAINT": (
            "A public recycling container that is damaged, missing, full, or not functioning "
            "properly. Sanitation repairs or replaces damaged recycling containers and "
            "adjusts pickup frequency for overflowing ones.",
            "Sanitation"),
        "RECYCLING ENFORCEMENT": (
            "A business or resident not following NYC recycling rules — failing to separate "
            "recyclables, placing recycling in wrong containers, or contaminating recycling "
            "streams with non-recyclable materials. Sanitation investigates and can issue "
            "violations to repeat offenders.",
            "Sanitation"),
        "REQUEST LARGE BULKY ITEM COLLECTION": (
            "A request to schedule pickup of large furniture or household appliances — "
            "such as sofas, mattresses, refrigerators, or washing machines — that cannot "
            "go in regular trash. NYC Sanitation provides scheduled bulk item pickup; "
            "items must be placed at the curb at the correct time.",
            "Sanitation"),
        "RESIDENTIAL DISPOSAL COMPLAINT": (
            "A resident is improperly disposing of household waste — placing garbage out "
            "before the legal time window (11 PM the night before collection), using "
            "non-compliant containers, placing recyclables in the wrong bin, or leaving "
            "bulk items on the curb without scheduling a special collection. Sanitation "
            "can issue violations; repeat offenders face escalating fines.",
            "Sanitation"),
        "SANITATION CONDITION": (
            "A general sanitation problem on a street, sidewalk, or public space that "
            "does not fit a more specific category — including accumulated debris, "
            "persistent odors, or unsanitary conditions not linked to a specific property. "
            "Sanitation investigates and coordinates the appropriate response.",
            "Sanitation"),
        "SANITATION WORKER OR VEHICLE COMPLAINT": (
            "A complaint about the conduct of a NYC Sanitation worker or the operation of "
            "a city garbage truck — including reckless or unsafe driving, failure to collect "
            "properly set-out garbage, leaving excessive spillage on the street, noise "
            "violations during overnight collection runs, or worker misconduct. Sanitation's "
            "Bureau of Investigations reviews and responds to complaints.",
            "Sanitation"),
        "SEASONAL COLLECTION": (
            "A request related to seasonal collection services — such as pickup of discarded "
            "Christmas trees in January, leaf collection in autumn, or other time-specific "
            "collection programs. NYC Sanitation runs seasonal campaigns with designated "
            "pickup dates and locations.",
            "Sanitation"),
        "SEWER": (
            "A blocked, overflowing, or broken sewer drain, catch basin, or manhole causing "
            "street flooding, sinkholes, sewage backup into buildings, or persistent foul "
            "odors. DEP manages NYC's sewer infrastructure and dispatches crews to unclog "
            "drains, repair broken sewer lines, or address sinkholes caused by underground "
            "pipe failures.",
            "DEP"),
        "SEWER MAINTENANCE": (
            "A request for routine maintenance on a city sewer line, catch basin, or "
            "related infrastructure — such as cleaning a catch basin, clearing a slow "
            "drain before it becomes a full blockage, or inspecting aging sewer pipes. "
            "DEP manages preventive maintenance of the sewer network.",
            "DEP"),
        "SNOW": (
            "Accumulated snow on a street, sidewalk, or public space that has not been "
            "plowed or cleared. NYC Sanitation manages snow removal on city streets; "
            "property owners are responsible for clearing sidewalks within four hours "
            "of snowfall ending.",
            "Sanitation/DOT"),
        "SNOW OR ICE": (
            "Snow or ice on a public sidewalk, stairway, or access ramp posing a slip "
            "and fall hazard. Property owners are legally required to clear sidewalks "
            "adjacent to their buildings within four hours after snow stops falling "
            "(or by 11 AM if it stops overnight). Sanitation can issue fines.",
            "Sanitation"),
        "SNOW REMOVAL": (
            "A request for snow removal from a specific street, intersection, or public "
            "space — particularly for locations that were missed during a snowstorm "
            "response, or for chronic problem areas such as intersections with deep drifts "
            "or bus stops. Sanitation prioritizes arterial streets and bus routes.",
            "Sanitation"),
        "SPECIAL NATURAL AREA DISTRICT (SNAD)": (
            "A violation of rules protecting a Special Natural Area District — designated "
            "zones in NYC containing significant natural features such as wetlands, forests, "
            "or ecological habitats. Development and land disturbance in SNADs requires "
            "special DOB and DCP approval. Violations may involve unauthorized construction "
            "or vegetation removal.",
            "DOB/DCP"),
        "STORM": (
            "Storm-related damage to streets, trees, infrastructure, or public property "
            "requiring city response — including downed trees, flooded roads, fallen power "
            "lines, or debris from high winds. OEM coordinates multi-agency storm response; "
            "Parks, Sanitation, and DOT each handle their respective infrastructure.",
            "Parks/Sanitation/DOT"),
        "STREET SWEEPING COMPLAINT": (
            "A street sweeper failed to clean a block on its scheduled day, leaving debris "
            "and dirt on the roadway, or a parked car received a street cleaning ticket on "
            "a block that was not actually swept that day. DOT manages the sweeping schedule; "
            "disputes about tickets issued on unswept blocks can be contested with evidence.",
            "Sanitation/DOT"),
        "SUSTAINABILITY ENFORCEMENT": (
            "A business or property violating NYC sustainability laws — including improper "
            "single-use plastic bag fees, violations of the commercial waste containerization "
            "law, or failure to comply with building energy efficiency requirements. DSNY "
            "and DCWP enforce sustainability regulations.",
            "DSNY/DCWP"),
        "SWEEPING/INADEQUATE": (
            "A street sweeper completed a pass on a scheduled block but did not adequately "
            "clean it — leaving significant debris on the curb or roadway. Sanitation "
            "investigates and may dispatch a follow-up sweep.",
            "Sanitation"),
        "SWEEPING/MISSED": (
            "A street sweeper completely missed a scheduled block — leaving it uncleaned "
            "on its designated sweeping day. Distinct from a general Street Sweeping "
            "Complaint which may also involve ticketing disputes. Sanitation investigates.",
            "Sanitation"),
        "TRANSFER STATION COMPLAINT": (
            "A complaint about a waste transfer station — a facility where garbage trucks "
            "deposit waste before it is transported to landfills or processing facilities. "
            "Includes complaints about odor, noise, truck traffic, operating outside "
            "permitted hours, or violations of environmental permits. DEP and Sanitation "
            "inspect.",
            "DEP/Sanitation"),
        "UPROOTED STUMP": (
            "A tree stump remaining on a sidewalk or street after a city tree removal — "
            "not yet ground down or removed. Stumps create tripping hazards and can "
            "continue to generate root growth. Parks Department schedules stump grinding "
            "as part of the tree removal follow-up.",
            "Parks"),
        "VACANT LOT": (
            "An overgrown, unsanitary, hazardous, or improperly maintained vacant lot — "
            "including high weeds and grass, accumulated garbage, open access inviting "
            "illegal dumping, or standing water. Property owners are legally responsible "
            "for maintaining their vacant lots. Sanitation and HPD can issue violations.",
            "Sanitation/HPD"),
        "WATER DRAINAGE": (
            "Inadequate drainage causing persistent standing water or flooding on a "
            "street, sidewalk, or public space — not linked to a specific broken pipe or "
            "sewer blockage. DEP and DOT assess drainage infrastructure and may install "
            "catch basins, grade adjustments, or inlet improvements.",
            "DEP/DOT"),
        "WATER MAINTENANCE": (
            "Routine maintenance needed on city water supply infrastructure — including "
            "aging water mains, hydrants, valves, or metering equipment. DEP manages "
            "preventive maintenance on NYC's water distribution network to prevent leaks "
            "and service interruptions.",
            "DEP"),
        "WOOD PILE REMAINING": (
            "Cut tree limbs, logs, wood chips, or other debris left on a public sidewalk "
            "or street after tree trimming or removal work by a city contractor or private "
            "arborist — not cleaned up at the conclusion of the job as required. Parks "
            "Department or Sanitation coordinates removal depending on whether the work "
            "was city-initiated or privately contracted.",
            "Parks/Sanitation"),
    },
    "🏠 Homeless, Safety & Social Services": {
        "DISORDERLY YOUTH": (
            "A group of young people behaving in a threatening, disruptive, or intimidating "
            "manner in a public space — including fighting, blocking pedestrian access, "
            "or engaging in vandalism. NYPD responds and may involve youth diversion "
            "programs or family court depending on the ages and circumstances.",
            "NYPD"),
        "DRUG ACTIVITY": (
            "Suspected open-air drug use, drug dealing, or related criminal activity in a "
            "public space such as a park, street corner, or building lobby — including "
            "visible drug paraphernalia, suspected hand-to-hand transactions, or groups "
            "gathered for apparent drug-related activity. NYPD may deploy narcotics units "
            "for locations with recurring complaints.",
            "NYPD"),
        "ENCAMPMENT": (
            "A group of individuals living in a tent, makeshift shelter, or semi-permanent "
            "encampment on public property — including parks, underpasses, transit areas, "
            "or sidewalks. NYC's Department of Homeless Services (DHS) and NYPD conduct "
            "outreach to connect individuals with shelter and services. Encampment removals "
            "follow a specific legal process that requires advance notice.",
            "DHS/NYPD"),
        "HOMELESS PERSON ASSISTANCE": (
            "An individual experiencing homelessness who appears to need outreach, shelter "
            "referral, or social services — but who is not in immediate medical distress. "
            "DHS outreach teams respond to connect the individual with shelter placement, "
            "mental health services, or other support. For medical emergencies involving "
            "a homeless person, call 911 — do not use 311.",
            "DHS"),
        "NON-EMERGENCY POLICE MATTER": (
            "A situation requiring police attention but not an active emergency — including "
            "suspicious activity, a minor dispute between neighbors, a suspicious package, "
            "a welfare check request, or general quality-of-life concerns. NYPD responds "
            "when available. Situations involving immediate danger to life should always "
            "be reported via 911, not 311.",
            "NYPD"),
        "PANHANDLING": (
            "Aggressive, persistent, or threatening solicitation of money in a public space "
            "— blocking pedestrian movement, following people, or making threatening "
            "statements while asking for money. Passive panhandling (quietly holding a sign) "
            "is generally protected as free speech under NYC law. NYPD responds only to "
            "aggressive or threatening panhandling behavior.",
            "NYPD"),
        "URINATING IN PUBLIC": (
            "A person urinating or defecating on a public street, sidewalk, park, or in a "
            "subway station. A quality-of-life violation under NYC Administrative Code. "
            "NYPD can issue summonses; the city also operates a network of public restrooms "
            "and supports expanded access as a harm reduction measure.",
            "NYPD"),
        "VENDOR ENFORCEMENT": (
            "An unlicensed street vendor operating without required permits, a licensed "
            "vendor operating outside their designated location or hours, or a vendor "
            "blocking pedestrian access or creating a safety hazard. NYC has complex "
            "vending regulations with different rules for food, merchandise, and veterans. "
            "DCWP and NYPD jointly enforce vending compliance.",
            "DCWP/NYPD"),
        "HOMELESS ENCAMPMENT": (
            "A group of homeless individuals camping or living in a public space — "
            "functionally similar to Encampment but often used for outdoor locations "
            "such as parks, underpasses, or near transit infrastructure. DHS outreach "
            "teams respond to offer shelter and services before any removal.",
            "DHS/NYPD"),
        "HOMELESS STREET CONDITION": (
            "General conditions associated with homeless activity on a street — including "
            "personal belongings left on the sidewalk, makeshift bedding, or other "
            "indicators of someone living on the street. DHS outreach teams are dispatched "
            "to assess needs and offer shelter placement.",
            "DHS"),
        "MASS GATHERING COMPLAINT": (
            "An unpermitted or disruptive large gathering in a public space — such as a "
            "block party, street fair, outdoor concert, or protest that is creating noise, "
            "blocking traffic, or posing a public safety concern. NYPD and DSNY respond "
            "depending on the nature and scale of the event.",
            "NYPD"),
        "PUBLIC TOILET": (
            "A public restroom that is locked when it should be open, vandalized, out of "
            "service, or in unsanitary condition. NYC Parks manages public restrooms in "
            "parks; DOT manages some street-level facilities. Complaints prompt inspection "
            "and restoration of service.",
            "Parks/DOT"),
        "QUALITY OF LIFE": (
            "A general quality-of-life complaint that does not fit a more specific "
            "category — including chronic nuisance behaviors, persistent neighborhood "
            "problems, or combinations of issues affecting residents' daily lives. "
            "Routed to the appropriate agency based on the nature of the complaint.",
            "Various"),
        "SMOKING": (
            "Smoking tobacco or other substances in a prohibited area — similar to "
            "Smoking or Vaping but may pre-date the vaping addition to the category. "
            "NYC's Smoke-Free Air Act prohibits smoking in parks, beaches, and near "
            "building entrances. NYPD or Health Department respond.",
            "Health/NYPD"),
        "UNLEASHED DOG": (
            "A dog running off-leash in an area where leashing is required — including "
            "sidewalks, streets, and parks outside of designated off-leash hours or zones. "
            "NYC parks allow off-leash dogs in designated areas during specific hours. "
            "Parks Enforcement Patrol and NYPD can issue summonses.",
            "Parks/NYPD"),
        "VENDING": (
            "A street vendor complaint covering licensing, location, hours of operation, "
            "or blocking pedestrian access — similar to Vendor Enforcement but used for "
            "broader vending-related issues that may not rise to the level of an "
            "enforcement action. DCWP and NYPD respond.",
            "DCWP/NYPD"),
        "VIOLATION OF PARK RULES": (
            "Any rule violation inside a city park — including consuming alcohol, grilling "
            "in prohibited areas, allowing dogs off-leash outside designated areas, "
            "trespassing after posted park hours, riding bikes in pedestrian zones, or "
            "conducting commercial activity without a permit. Parks Enforcement Patrol "
            "(PEP) officers can issue summonses for violations.",
            "Parks"),
    },
    "🏗️ Buildings, Utilities & Maintenance": {
        "APPLIANCE": (
            "A landlord-provided appliance in a residential rental unit — such as a stove, "
            "refrigerator, or heating appliance — that is broken, malfunctioning, or unsafe. "
            "NYC law requires landlords to maintain all appliances they supply as part of "
            "the rental agreement. HPD inspects and can issue violations requiring repair "
            "or replacement at the landlord's expense.",
            "HPD"),
        "DAY CARE": (
            "A complaint about a licensed or unlicensed day care center, home day care, or "
            "childcare facility — including unsafe physical conditions, overcrowding beyond "
            "licensed capacity, untrained or inadequate staff, lack of supervision, or "
            "operation without a required license. The Administration for Children's "
            "Services (ACS) and Health Department inspect and can revoke licenses or close "
            "facilities posing risks to children.",
            "ACS/Health"),
        "ELECTRIC": (
            "An electrical hazard or service outage in a residential building — including "
            "exposed or sparking wiring, outlets that don't work, tripped circuit breakers "
            "the landlord refuses to address, flickering power affecting the whole unit, "
            "or complete loss of electricity. NYC law requires landlords to maintain safe "
            "electrical systems. HPD inspects; severe hazards may trigger emergency response "
            "from Con Edison.",
            "HPD/ConEd"),
        "ELECTRICAL": (
            "An electrical issue in a commercial building, public space, or non-residential "
            "structure — including faulty wiring, power outages, or unsafe electrical "
            "installations in offices, retail stores, or public facilities. DOB inspects "
            "commercial electrical systems; Con Edison responds to utility-side faults and "
            "outages affecting commercial properties.",
            "DOB/ConEd"),
        "EMERGENCY RESPONSE TEAM (ERT)": (
            "A structural emergency requiring immediate assessment by the Department of "
            "Buildings Emergency Response Team — including a partially collapsed ceiling or "
            "wall, a building struck by a vehicle, imminent facade failure, or any condition "
            "where a structure appears at risk of catastrophic failure. ERT engineers respond "
            "24/7. FDNY and NYPD are typically co-dispatched. If a collapse appears imminent, "
            "call 911 immediately — do not wait for a 311 response.",
            "DOB/FDNY"),
        "GENERAL": (
            "A catch-all category for complaints that do not fit any specific type in the "
            "311 system at the time of filing. These are reviewed by the appropriate agency "
            "and reassigned or passed to the relevant department. A high volume of General "
            "complaints in one area may indicate an emerging issue not yet captured by "
            "existing categories.",
            "Various"),
        "GENERAL CONSTRUCTION/PLUMBING": (
            "Construction or plumbing work being performed without required NYC Department "
            "of Buildings permits, outside legally permitted working hours (typically 7 AM "
            "to 6 PM on weekdays), in an unsafe manner, or in violation of approved plans. "
            "Unpermitted work bypasses inspections designed to ensure structural and "
            "life-safety standards are met. DOB inspectors can issue stop-work orders and "
            "substantial fines.",
            "DOB"),
        "MAINTENANCE OR FACILITY": (
            "A city-owned facility, building, or piece of infrastructure in need of "
            "maintenance — including broken equipment in a park, a damaged community center, "
            "a broken fence in a schoolyard, or a malfunctioning light in a city-owned "
            "parking facility. The complaint is routed to the appropriate city agency based "
            "on the specific asset type and location.",
            "Various"),
        "BEST/SITE SAFETY": (
            "A safety complaint related to a construction site that falls under DOB's "
            "Builders and Enforcement Safety Team (BEST) program — including inadequate "
            "barriers, missing hard hats, unsecured materials, or other site safety "
            "violations posing risks to workers or the public. DOB's BEST squad inspects "
            "and can issue stop-work orders.",
            "DOB"),
        "BUILDING/USE": (
            "A complaint about a building being used for a purpose other than what it is "
            "legally permitted for — such as a residential building being used as a hotel, "
            "a garage converted to living space without permits, or a commercial space "
            "operating as an illegal nightclub. DOB and DCP investigate zoning and use "
            "violations.",
            "DOB/DCP"),
        "CONSTRUCTION LEAD DUST": (
            "Lead dust generated by construction, renovation, or demolition work in a "
            "building — particularly from sanding or disturbing lead-based paint in "
            "pre-1978 buildings. Lead dust is highly hazardous especially for children. "
            "DEP requires dust containment and worker protection measures; violations "
            "can result in stop-work orders.",
            "DEP/DOB"),
        "CONSTRUCTION SAFETY ENFORCEMENT": (
            "A broad construction site safety violation — including failure to maintain "
            "required safety plans, inadequate worker protection equipment, unsafe crane "
            "operations, or other conditions violating NYC Building Code safety requirements. "
            "DOB inspectors respond and can issue violations and stop-work orders.",
            "DOB"),
        "COOLING TOWER": (
            "A complaint about an improperly maintained or unsanitary cooling tower on a "
            "building rooftop. Cooling towers can harbor Legionella bacteria, which causes "
            "Legionnaires' disease — a severe form of pneumonia. NYC requires quarterly "
            "inspections and regular disinfection of all cooling towers. DEP enforces.",
            "DEP"),
        "COVID-19 NON-ESSENTIAL CONSTRUCTION": (
            "A construction site operating in violation of NYC's COVID-19 emergency order "
            "restricting non-essential construction during the pandemic. Active during "
            "spring 2020. Historical data reflects the early pandemic enforcement period.",
            "DOB"),
        "CRANES AND DERRICKS": (
            "A safety concern with a crane or derrick at a construction site — including "
            "improper setup, operation by an uncertified operator, inadequate safety "
            "inspections, or positioning that creates risk to pedestrians and nearby "
            "buildings. DOB crane inspectors respond; crane accidents are treated as "
            "immediate emergencies.",
            "DOB"),
        "DOB POSTED NOTICE OR ORDER": (
            "A complaint about a DOB vacate order, stop-work order, or other official "
            "notice posted on a building that may not be properly followed — such as a "
            "building that has been vacated but where occupants remain, or construction "
            "continuing under a stop-work order. DOB enforces compliance.",
            "DOB"),
        "FACADE INSP SAFETY PGM": (
            "A complaint or report triggering a facade safety inspection under NYC's "
            "Facade Inspection Safety Program (FISP) — which requires buildings over "
            "six stories to have their facades inspected every five years. Reports may "
            "involve visible deterioration, spalling, or cracking on a building facade. "
            "DOB coordinates inspections.",
            "DOB"),
        "FACADES": (
            "Unsafe conditions on a building's exterior facade — including crumbling "
            "brick, loose stone, deteriorating terra cotta, or other materials at risk "
            "of falling. A facade complaint triggers a DOB inspection; severe conditions "
            "can result in mandatory sidewalk sheds or emergency repairs.",
            "DOB"),
        "SAFETY": (
            "A general safety hazard in a public space or building that does not fit a more "
            "specific complaint category — such as a broken fence around a construction "
            "site, an unsecured basement hatch on a sidewalk, a dangerously loose overhead "
            "fixture, or any condition posing an immediate risk of injury to the public. "
            "Routed to DOB, DOT, or Parks depending on the nature and location of the "
            "hazard.",
            "Various"),
        "SCAFFOLD SAFETY": (
            "Unsafe scaffolding on a building — including scaffolding that is improperly "
            "braced, missing required safety netting, installed without a permit, or "
            "showing signs of structural failure. Scaffold failures can cause fatalities. "
            "DOB inspects and can require immediate remediation or removal.",
            "DOB"),
        "SCHOOL MAINTENANCE": (
            "A maintenance issue in a NYC public school building — including broken "
            "heating systems, damaged facilities, pest infestations, or structural "
            "concerns. The NYC School Construction Authority (SCA) and DOE facilities "
            "division manage school building maintenance.",
            "DOE/SCA"),
        "SPECIAL PROJECTS INSPECTION TEAM (SPIT)": (
            "A complex or multi-violation building complaint handled by DOB's Special "
            "Projects Inspection Team — typically involving buildings with multiple "
            "outstanding violations, illegal conversions, or complex structural issues "
            "requiring specialized inspectors. DOB's SPIT unit coordinates multi-faceted "
            "investigations.",
            "DOB"),
        "STALLED SITES": (
            "An abandoned or stalled construction site that has been inactive for an "
            "extended period — posing safety hazards including unsecured excavations, "
            "exposed structural elements, deteriorating temporary protections, or "
            "standing water. DOB's Stalled Sites Program monitors and enforces "
            "required site security measures.",
            "DOB"),
    },
    "🚕 Taxi & Transportation": {
        "DISPATCHED TAXI COMPLAINT": (
            "A complaint about a taxi dispatched through a car service or black car "
            "company — including overcharging, refusal to take a trip, unsafe driving, "
            "or driver misconduct. TLC investigates and can suspend or revoke the "
            "driver's license.",
            "TLC"),
        "DISPATCHED TAXI COMPLIMENT": (
            "Positive feedback about a dispatched taxi or car service driver — recognized "
            "for exceptional service, honesty, or professionalism. TLC records compliments "
            "in driver profiles.",
            "TLC"),
        "FHV LICENSEE COMPLAINT": (
            "A complaint about the licensee (owner or operator) of a For-Hire Vehicle "
            "company — such as a black car base, limousine company, or dispatch service — "
            "rather than an individual driver. Covers operating without proper licensing, "
            "misrepresenting services, or systemic driver conduct issues. TLC investigates.",
            "TLC"),
        "FERRY COMPLAINT": (
            "A complaint about NYC Ferry service — including vessel conditions, safety "
            "concerns, crew conduct, accessibility issues, or service disruptions on the "
            "city-operated ferry network. NYC DOT and the ferry operator (operated under "
            "contract) respond.",
            "DOT"),
        "FERRY INQUIRY": (
            "An inquiry or information request about NYC Ferry routes, schedules, fares, "
            "or services — not a complaint about a problem. Routed to NYC DOT ferry "
            "operations for response.",
            "DOT"),
        "FOR HIRE VEHICLE COMPLAINT": (
            "A complaint about a for-hire vehicle driver — including Uber, Lyft, or "
            "black car drivers — covering unsafe driving, overcharging, refusal of service, "
            "discrimination, or inappropriate conduct. TLC investigates and can suspend "
            "or revoke driver authorization.",
            "TLC"),
        "FOR HIRE VEHICLE REPORT": (
            "A report related to a for-hire vehicle incident — such as an accident, "
            "lost item, or other matter that requires documentation but may not rise "
            "to the level of a formal complaint. TLC records reports for monitoring.",
            "TLC"),
        "GREEN TAXI COMPLAINT": (
            "A complaint about a green (boro) taxi driver or vehicle — covering unsafe "
            "driving, overcharging, refusal to take a passenger, or vehicle condition "
            "issues. Green taxis serve the outer boroughs and northern Manhattan. "
            "TLC investigates.",
            "TLC"),
        "GREEN TAXI REPORT": (
            "A report related to a green taxi — such as a lost item left in the vehicle "
            "or an incident requiring documentation. TLC records and routes accordingly.",
            "TLC"),
        "TAXI COMPLAINT": (
            "A complaint about a yellow taxi cab — including overcharging, refusing to "
            "take a passenger or destination, unsafe or reckless driving, vehicle in "
            "poor condition, or driver misconduct. TLC investigates all complaints and "
            "can suspend or revoke a driver's hack license.",
            "TLC"),
        "TAXI COMPLIMENT": (
            "Positive feedback about a yellow taxi driver — for honesty (returning "
            "forgotten items), exceptional service, safe driving, or professionalism. "
            "TLC records compliments which can be referenced in driver performance "
            "evaluations.",
            "TLC"),
        "TAXI LICENSEE COMPLAINT": (
            "A formal complaint against a specific TLC-licensed taxi driver — covering "
            "serious violations including harassment, discrimination, assault, or "
            "repeated pattern violations. TLC's enforcement division investigates and "
            "can pursue disciplinary action including license revocation.",
            "TLC"),
        "TAXI REPORT": (
            "A general informational report related to yellow taxi activity — including "
            "a traffic accident involving a cab, a witnessed violation, or information "
            "that does not constitute a formal complaint. TLC uses reports for monitoring "
            "and trend analysis.",
            "TLC"),
    },
    "🏛️ City Services & Infrastructure": {
        "ADOPT-A-BASKET": (
            "A request or inquiry related to NYC's Adopt-A-Basket program — where "
            "community members or businesses volunteer to regularly empty and maintain "
            "a public litter basket. Sanitation coordinates the program.",
            "Sanitation"),
        "BENCH": (
            "A damaged, missing, or improperly placed public bench — in a park, transit "
            "area, or public plaza. Parks Department repairs or replaces benches in city "
            "parks; DOT manages benches in public plazas and along streets.",
            "Parks/DOT"),
        "BUS STOP SHELTER COMPLAINT": (
            "A complaint about a damaged, dirty, graffiti-covered, or obstructed bus "
            "stop shelter. NYC DOT manages bus stop shelters through a vendor contract. "
            "Complaints trigger inspection and repair or cleaning.",
            "DOT"),
        "BUS STOP SHELTER PLACEMENT": (
            "A request for a new bus stop shelter to be installed at a stop that currently "
            "lacks one. DOT evaluates requests based on ridership, available space, and "
            "infrastructure priorities.",
            "DOT"),
        "EMPLOYEE BEHAVIOR": (
            "A complaint about the conduct or professionalism of a NYC city employee — "
            "including discourteous behavior, failure to respond appropriately, or "
            "unprofessional conduct during the course of their duties. Routed to the "
            "relevant agency's internal affairs or HR department.",
            "Various"),
        "FOUND PROPERTY": (
            "A report of found property left in a public space, city facility, or "
            "transit area — to be logged and potentially returned to its owner. "
            "Routed to NYPD property clerk or the relevant agency depending on "
            "where the item was found.",
            "NYPD"),
        "LEANING BAR": (
            "A complaint about a leaning bar, barricade, or support structure — typically "
            "associated with construction scaffolding or protective pedestrian walkways "
            "that are improperly installed, damaged, or pose a hazard. DOB or DOT "
            "responds depending on the structure.",
            "DOB/DOT"),
        "LIFEGUARD": (
            "A complaint or concern about lifeguard presence, conduct, or response at "
            "a city beach or public pool — including insufficient coverage, inappropriate "
            "behavior, or concerns about emergency response capability. Parks Department "
            "manages NYC's public beach and pool lifeguard program.",
            "Parks"),
        "LINKNYC": (
            "A complaint about a LinkNYC kiosk — the city's public Wi-Fi and digital "
            "services infrastructure — including a malfunctioning unit, vandalized screen, "
            "inappropriate content displayed, or kiosk blocking pedestrian access. "
            "The LinkNYC operator responds to service complaints.",
            "DOT"),
        "LOST PROPERTY": (
            "A report of lost personal property in a public space or city facility — "
            "to initiate a search or record the loss. NYPD property clerk handles lost "
            "items reported in public spaces; relevant agencies handle losses in "
            "their facilities.",
            "NYPD"),
        "MISCELLANEOUS CATEGORIES": (
            "A complaint that does not fit any established 311 category at the time of "
            "filing. Used as a placeholder for emerging issues or unusual complaints. "
            "City staff review and route to the appropriate agency.",
            "Various"),
        "PLANT": (
            "A complaint about a plant or vegetation on public property — such as an "
            "invasive species encroaching on a sidewalk, overgrown shrubs blocking "
            "sightlines, or vegetation from private property encroaching on public "
            "space. Parks Department or DOT responds depending on location.",
            "Parks/DOT"),
        "PUBLIC PAYPHONE COMPLAINT": (
            "A complaint about a public payphone — damaged, vandalized, out of service, "
            "or being used for illegal activity. NYC has a limited legacy payphone "
            "network; most payphone infrastructure is being converted to LinkNYC kiosks. "
            "DOT manages public payphone contracts.",
            "DOT"),
        "WAYFINDING": (
            "A complaint about or request for directional signage in public spaces — "
            "including missing, damaged, or confusing wayfinding signs in parks, plazas, "
            "or public buildings. Parks Department and DOT manage public wayfinding systems.",
            "Parks/DOT"),
    },
    "⚙️ Internal & Administrative": {
        "AHV INSPECTION UNIT": (
            "Internal routing code used by the TLC's Accessible Human Vehicle (AHV) "
            "inspection unit. Not a public complaint type — used internally to track "
            "inspection cases.",
            "TLC"),
        "BOROUGH OFFICE": (
            "A complaint or inquiry routed directly to a borough commissioner's office "
            "for review and response — typically involving issues that require executive "
            "attention or fall outside standard complaint routing.",
            "Various"),
        "BUILDING MARSHAL'S OFFICE": (
            "A case handled by or referred to the NYC Buildings Marshal's Office — "
            "which enforces court orders related to vacate orders, demolition requirements, "
            "or building code compliance. Internal routing code.",
            "DOB"),
        "BUILDING MARSHALS OFFICE": (
            "Variant spelling of Building Marshal's Office. Same function — internal "
            "routing to the DOB Buildings Marshal's enforcement unit.",
            "DOB"),
        "DEPT OF INVESTIGATIONS": (
            "A matter referred to the NYC Department of Investigations (DOI) for review — "
            "typically involving suspected corruption, fraud, or serious misconduct by a "
            "city employee or contractor. Internal routing code.",
            "DOI"),
        "DSNY INTERNAL": (
            "Internal Sanitation Department communication or case — not a public-facing "
            "complaint. Used for internal tracking of operational matters.",
            "Sanitation"),
        "EXECUTIVE INSPECTIONS": (
            "A priority inspection requested at the executive or commissioner level of "
            "a city agency — typically for politically sensitive or high-profile locations. "
            "Internal routing code.",
            "Various"),
        "INCORRECT DATA": (
            "A correction request for inaccurate data entered into the 311 system — "
            "such as a wrong address, misclassified complaint type, or erroneous "
            "information. Internal data quality routing.",
            "311"),
        "INTERNAL CODE": (
            "A general internal routing code used by city agencies for tracking purposes "
            "— not associated with a public complaint. May appear in historical data "
            "from legacy system migrations.",
            "Various"),
        "INVESTIGATIONS AND DISCIPLINE (IAD)": (
            "An employee conduct investigation routed to an agency's Internal Affairs "
            "Division (IAD) — covering allegations of misconduct, excessive force, "
            "corruption, or other serious violations by city employees.",
            "Various"),
        "OTHER ENFORCEMENT": (
            "An enforcement action that does not fit an established complaint category — "
            "used internally when agencies take action outside standard complaint types. "
            "Internal routing code.",
            "Various"),
        "REAL TIME ENFORCEMENT": (
            "An enforcement response deployed in real time — typically used when an "
            "inspector or officer directly observes a violation without a prior complaint. "
            "Internal tracking code.",
            "Various"),
        "SPECIAL OPERATIONS": (
            "A special operational matter handled within a specific city agency — not "
            "a public complaint. Used for coordinated multi-agency operations or "
            "targeted enforcement campaigns.",
            "Various"),
        "SRDE": (
            "Internal Sanitation Department routing code. Not a public complaint type — "
            "used for internal operational tracking.",
            "Sanitation"),
        "SRGOVG": (
            "Internal city government routing code. Not a public complaint type — "
            "used for internal administrative tracking.",
            "Various"),
        "UNSPECIFIED": (
            "Complaint type not specified at the time of filing — used when a caller "
            "or online submitter did not identify a specific issue category. City staff "
            "follow up to reclassify.",
            "Various"),
        "ZTESTINT": (
            "Internal test entry used by city IT systems to verify 311 system "
            "functionality. Not a real complaint — appears in historical data from "
            "system testing.",
            "311"),
    },
}

# Flat lookup: complaint_type → (description, agency, category) for O(1) access
_LOOKUP: dict[str, tuple[str, str, str]] = {
    ctype: (desc, agency, cat)
    for cat, complaints in COMPLAINT_TYPES.items()
    for ctype, (desc, agency) in complaints.items()
}


@st.cache_data(ttl=3600)
def _live_complaint_types() -> list[str]:
    """Distinct complaint types present in Snowflake, sorted alphabetically."""
    try:
        return (
            run_query("SELECT DISTINCT complaint_type FROM MARTS.FCT_EQUITY_SPLITS ORDER BY 1")[
                "complaint_type"
            ].tolist()
        )
    except Exception:
        # Snowflake unavailable — fall back to the hardcoded set so the page still renders
        return sorted(_LOOKUP.keys())


_live_types = _live_complaint_types()

# Partition live types into known (has a description) and uncategorized
_by_category: dict[str, list[str]] = defaultdict(list)
_uncategorized: list[str] = []
for _t in _live_types:
    if _t in _LOOKUP:
        _by_category[_LOOKUP[_t][2]].append(_t)
    else:
        _uncategorized.append(_t)


with st.expander("Show all complaint types and what they mean"):
    st.markdown(
        "**Agency abbreviations:** HPD = Housing Preservation & Development · "
        "DOB = Dept of Buildings · DEP = Dept of Environmental Protection · "
        "DOT = Dept of Transportation · DHS = Dept of Homeless Services · "
        "TLC = Taxi & Limousine Commission · FDNY = Fire Dept · "
        "NYPD = Police Dept · ACC = Animal Care Centers"
    )
    st.markdown("---")

    search = st.text_input("🔍 Search complaint types", placeholder="e.g. food, noise, heat...")
    q = search.strip().lower()

    # ── Described categories (preserve original display order) ────────────────
    for category in COMPLAINT_TYPES:
        types_in_cat = _by_category.get(category, [])
        rows = []
        for ctype in types_in_cat:
            desc, agency, _ = _LOOKUP[ctype]
            if not q or q in ctype.lower() or q in desc.lower():
                rows.append({"Complaint Type": ctype, "What it means": desc, "Agency": agency})
        if not rows:
            continue
        st.markdown(f"**{category}**")
        # st.table wraps text naturally — st.dataframe clips long text at fixed row height
        st.table(pd.DataFrame(rows).set_index("Complaint Type"))

    # ── Types in Snowflake that have no hardcoded description yet ─────────────
    if _uncategorized:
        unc_rows = [
            {
                "Complaint Type": t,
                "What it means": (
                    "A valid NYC 311 complaint category. "
                    "Detailed description not yet available in this reference."
                ),
                "Agency": "Various",
            }
            for t in _uncategorized
            if not q or q in t.lower()
        ]
        if unc_rows:
            st.markdown("**📋 Other / Uncategorized**")
            st.table(pd.DataFrame(unc_rows).set_index("Complaint Type"))

st.markdown(BACK_TO_TOP)
st.divider()

# ── The Problem ───────────────────────────────────────────────────────────────
st.subheader("The Problem")
st.markdown("""
The question this dashboard asks is simple: **does the city respond equally fast to everyone?**

Research and resident experience suggest the answer is no. Neighborhoods with lower household
incomes tend to wait longer for the same types of complaints to be resolved compared to wealthier
neighborhoods — even when the complaints are identical. This is a **service equity** problem.
""")


st.markdown(BACK_TO_TOP)
st.divider()

# ── What is a Census Tract ────────────────────────────────────────────────────
st.subheader("What is a Census Tract?")

col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("""
    New York City is divided into **2,168 census tracts** — small geographic units defined by
    the US Census Bureau. Each tract contains roughly **1,200 to 8,000 people**.

    Think of census tracts as the city's smallest official neighborhood units. They are:
    - Smaller than ZIP codes
    - More precise than borough-level analysis
    - Stable enough to track changes over time

    The US Census Bureau surveys every census tract every year through the
    **American Community Survey (ACS)** — collecting data on income, population, poverty rates,
    and demographics. This dashboard uses that data to assign each tract an **income quintile**:

    | Quintile | Meaning | Approx. median income |
    |---|---|---|
    | 1 | Lowest income — bottom 20% of tracts | Below ~$35,000/year |
    | 2 | Lower-middle income | ~$35,000–$55,000 |
    | 3 | Middle income | ~$55,000–$75,000 |
    | 4 | Upper-middle income | ~$75,000–$100,000 |
    | 5 | Highest income — top 20% of tracts | Above ~$100,000 |

    > **Example:** Brownsville, Brooklyn is a quintile 1 tract.
    > The Upper East Side, Manhattan is a quintile 5 tract.
    > This dashboard measures whether they receive the same quality of 311 service.
    """)
with col2:
    st.info("""
    **NYC's 5 Boroughs:**

    🟫 **Manhattan** — densely packed island, home to both the wealthiest and some of the
    poorest neighborhoods in the city

    🟧 **Brooklyn** — most populous borough, wide income diversity from Brownsville to
    Brooklyn Heights

    🟨 **Queens** — most ethnically diverse borough, large immigrant communities

    🟥 **The Bronx** — highest poverty rate of any US urban county

    🟩 **Staten Island** — least densely populated, predominantly suburban character
    """)

st.markdown(BACK_TO_TOP)
st.divider()

# ── Key Metrics Explained ─────────────────────────────────────────────────────
st.subheader("Key Metrics Explained")

st.markdown("##### Response Time")
st.markdown("""
Response time is measured in **hours** from when a 311 request is submitted to when the
assigned agency marks it as resolved.

This dashboard uses **percentiles** rather than averages because averages are easily skewed
by extreme outliers (a single complaint that took 6 months would distort the whole borough's average).

**Important:** all percentiles are computed **within a single tract over its complaint history**
— not across the city. A P90 of 72 hours for a tract means that 90% of complaints of that
type filed in *that specific neighborhood* resolved within 72 hours, based on its historical record.
It is not saying 90% of NYC complaints resolved in 72 hours.

| Metric | What it means | Scope |
|---|---|---|
| **P50 (median)** | Half of this tract's complaints resolved faster, half slower | Per tract, over time |
| **P75** | 75% of this tract's complaints resolved within this time | Per tract, over time |
| **P90** | 90% of this tract's complaints resolved within this time — the worst-case experience for this neighborhood | Per tract, over time |

This dashboard focuses on **P90** because it best captures whether the *worst-served* residents
in a specific neighborhood are being left behind — independently of what happens elsewhere in the city.
""")

st.markdown("##### Equity Score")
st.markdown("""
The equity score is the core metric of this dashboard.

> **Equity Score = This tract's P90 ÷ Median tract P90 for the same complaint type and month**

Both the numerator and the denominator are tract-level P90s — not city-wide raw complaint
averages. The numerator is this specific tract's historical worst-case response time (90th
percentile of all complaints filed there). The denominator is the **median of all tract P90s**
citywide for that complaint type — the middle value when you rank every neighborhood by its
own P90.

**Why this matters:**

A volume-weighted city average is skewed by whichever boroughs file the most complaints for a
given type. High-volume areas dominate the denominator, which either artificially inflates scores
for tracts in under-represented areas or hides genuine inequity for low-volume tracts by averaging
their slow service down against faster high-volume neighbors.

Using the median of tract P90s fixes both problems:
- Every neighborhood gets **one equal vote** in the baseline, regardless of complaint volume
- The denominator reflects the **structural service pattern of a typical tract**, not the weighted
  sum of complaint activity across the city
- A score of 1.0 means this tract's worst-case experience matches the median neighborhood —
  half of NYC tracts perform better, half perform worse

**Concrete example:**
Noise complaints are concentrated in Manhattan where NYPD responds in ~2 hours. Under a
volume-weighted average, the baseline collapses to ~2 hours. A Bronx tract resolving the same
complaints in 4 hours scores 2.0 — looks like a crisis. Under the median-tract baseline, the
4-hour Bronx tract is compared against the actual midpoint of all neighborhood experiences, not
Manhattan's volume. The score reflects reality.

| Score | Meaning |
|---|---|
| `1.0` | This tract matches the **typical NYC neighborhood** — half of tracts are faster, half are slower |
| `1.5` | Residents here wait 50% longer than the typical neighborhood for this complaint type |
| `2.0` | Residents here wait twice as long as the typical neighborhood |
| `0.8` | Residents here wait 20% less — faster service than most neighborhoods |

An equity score consistently above 1.0 for lower-income tracts — and below 1.0 for
higher-income tracts — is evidence of a **systematic service disparity** that cannot be
explained by complaint volume or geographic concentration alone.
""")

st.markdown(BACK_TO_TOP)
st.divider()

# ── How to Navigate ───────────────────────────────────────────────────────────
st.subheader("How to Navigate This Dashboard")

st.markdown("""
Use the **sidebar on the left** to switch between pages:

| Page | What it shows |
|---|---|
| 🗺️ **Borough Map** | A color-coded map of every NYC census tract. Green tracts receive on-par or better service. Red tracts wait significantly longer. Filter by complaint type and borough to focus on specific issues. |
| 📊 **Equity by Income** | Bar charts and scatter plots showing whether lower-income quintiles wait longer than higher-income ones for the same complaint type. The equity ratio callout gives a single number summary. |
| 🔥 **Complaint Breakdown** | A heatmap of the top 20 complaint types across all 5 boroughs. Reveals which categories have the worst response times and where. |
| 🔍 **Key Findings** | Three specific findings drawn from the data — rodent complaint gaps by income, heat complaint disparities by borough in winter, and how the equity gap has changed over time. |

**Start with the Borough Map** — select a complaint type you care about and look for clusters
of red tracts. Then use the Equity by Income page to quantify the gap, and the Key Findings
page to see the headline numbers.
""")

st.markdown(BACK_TO_TOP)
st.divider()

# ── Data Sources ──────────────────────────────────────────────────────────────
st.subheader("Data Sources")
st.markdown("""
| Source | What it provides | Updated |
|---|---|---|
| [NYC Open Data — 311 Service Requests](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9) | Every 311 request submitted to the city | Daily |
| [US Census Bureau — ACS 5-Year Estimates](https://www.census.gov/programs-surveys/acs) | Tract-level demographics: income, population, poverty | Annually |
| [NYC Census Tract Boundaries](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Geographic boundaries for each census tract | Decennial |

All data is processed through an automated pipeline that ingests new 311 requests daily,
joins them to their census tract using GPS coordinates, and recomputes equity metrics across
all tracts. The dashboard reflects the most recent data loaded.
""")

st.markdown(BACK_TO_TOP)
st.caption("Built with Socrata API · AWS S3 · Snowflake · dbt · Great Expectations · Streamlit")
