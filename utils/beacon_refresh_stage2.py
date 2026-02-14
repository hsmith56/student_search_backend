from concurrent.futures import ThreadPoolExecutor
import logging
import math
import re
from datetime import datetime
from pathlib import Path

import json
from core.config import settings
from integrations.beacon_client import beacon_client
from repositories.students import insert_full_student
from requests.exceptions import JSONDecodeError


sports_mapping_json_p = (
    Path(__file__).resolve().parent.parent / "data" / "sports_interests.json"
)
state_mapping_json_p = (
    Path(__file__).resolve().parent.parent / "data" / "state_mappings.json"
)

sports_interests_mappings = json.load(open(sports_mapping_json_p, "r"))
sports_interests_mappings = {
    x["id"]: x["description"] for x in sports_interests_mappings
}

state_mappings_orig = json.load(open(state_mapping_json_p, "r"))
state_mappings = {x["id"]: x["name"] for x in state_mappings_orig}

BASE_URL = settings.beacon_base_url
THREADS = settings.beacon_threads
logger = logging.getLogger(__name__)

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://beacon.ciee.org/participant/313628",
    "Origin": "https://beacon.ciee.org",
    "DNT": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Sec-GPC": "1",
}


def get_basic_information(application_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/participant/phi/application/{application_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_category_mappings(application_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/sections/standardtype/{application_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_health_information(field_id):
    # {"participantId":182394,"hasHospitalized":false,"hospitalizedComment":"","hasConsultedNervousSpecialist":false,
    # "consultedNervousSpecialistComment":"","takingAnyMedications":false,"takingAnyMedicationsComment":"",
    # "hasAnyAllergies":false,"anyAllergiesComment":"","hasAnyPhysicalDisability":false,
    # "anyPhysicalDisabilityComment":"","hasPreexistingMedicalConditions":false,"preexistingMedicalConditionsComment":"",
    # "isThereAnyMedicalInfoImportantForCIEE":false,"anyMedicalInfoImportantForCIEEComment":"",
    # "isFullyVaccinatedAgainstCovid19":true}
    response = beacon_client.get(
        f"{BASE_URL}/beacon/participant/hsjhealthInformation/{field_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_personal_information(field_id):
    # {"religion":"atheist","religiousServiceAttendanceFrequencyId":0, "genderExplanation": "not applicable"
    # "religionImportantToAttendServices":false,"dietSpecial":false,"dietComment":"","dietCanAlter":true,
    # "environmentSmoke":false,"environmentLiveWithFamilyWhoSmokes":false,"environmentLiveWithPets":false,"
    # environmentLiveWithPetsComment":"I am allergic to pet fur.","environmentAllergies":true,
    # "environmentAllergiesComment":"Pet fur, hay, pollen, carrots, dry grass","earliestArrivalDate":"",
    # "latestDepartureDate":""}
    response = beacon_client.get(
        f"{BASE_URL}/beacon/Participant/ppi/section/{field_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_interests_hobbies(field_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/Participant/psii/section/{field_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_host_family_messages(field_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/Participant/hostfamilymessages/{field_id}",
        headers=BASE_HEADERS,
    )
    return response


def get_photo_details(application_id):
    comments = ""
    url = f"{BASE_URL}/beacon/File/GetS3DocumentUrls/{application_id}/Other%20Photos"
    response = beacon_client.get(url, headers=BASE_HEADERS)
    try:
        json_response = response.json()
    except JSONDecodeError:
        return comments

    for pictures in json_response:
        for key, value in pictures.items():
            if key == "comment" and len(value) != "":
                comments = comments + "|" + value

    return comments


def get_program_type(application_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/Participant/{application_id}",
        headers=BASE_HEADERS,
    )
    return response.json()["productName"]


def get_placement_requests(field_id):
    """
    {"participantId":224308,"productYear":2025,"roomPlacementId":2,"isHasPrePlacement":false,"prePlacementFamilyName":null,
    "prePlacementFamilyPhone":null,"prePlacementFamilyEmail":null,"prePlacementFamilyAddress":null,"prePlacementFamilySchool":null,
    "prePlacementSchoolConnection":null,"isInterestedInStandardPlacement":null,"regionPlacementId":null,"statePlacementId":null,
    "coastalPlacementId":3,"urbanPlacementId":5,"californiaPlacementId":14,"floridaPlacementId":null,"tuitionPlacementConsidered":false,
    "tuitionPlacementId":null,"wantToAttendArrivalOrientation":null,"cieehsDiploma":null,"cieeSelectExperience":true,
    "willingToAcceptSinglePersonPlacement":true,"willingToAcceptDoublePlacement":true,"electiveOptionsConfirmed":true,"potentialPreplacement":null,
    "regionalOrStatePlacementPreferred":"No","needCIEECollegeCounselorsAssistance":"No","collegePrepCounselingOptionId":null,
    "essentialsCounselingOptionsIds":[],"essentialsCounselingOptionsIdsCount":null,"placementElectiveWarmRegionRequested":null,
    "placementElectiveStudentEnrollmentGreaterThan500Requested":null,"placementElectiveSportsOpportunityRequested":null,
    "placementElectiveNewEnglandRequested":null,"placementElectiveThreeStatesRequested":false,"placementElectiveState1Id":null,
    "placementElectiveState2Id":null,"placementElectiveState3Id":null,"placementElectiveStates":"","placementElectiveFiveStatesRequested":false,
    "placementElectiveFiveState1Id":null,"placementElectiveFiveState2Id":null,"placementElectiveFiveState3Id":null,"placementElectiveFiveState4Id":null,
    "placementElectiveFiveState5Id":null,"placementElectiveFiveStates":"","placementElectiveEarlyDecisionMayRequested":null,"placementElectiveEarlyDecisionJuneRequested":null,
    "placementElectiveEarlyDecisionAprilRequested":false,"placementElectiveEarlyDecisionNovemberRequested":false}


    """

    response = beacon_client.get(
        f"{BASE_URL}/beacon/Participant/j1placement/{field_id}",
        headers=BASE_HEADERS,
    )
    r_json = response.json()
    single_placement = r_json.get("willingToAcceptSinglePersonPlacement")
    double_placement = r_json.get("willingToAcceptDoublePlacement")
    pre_p = r_json.get("isInterestedInStandardPlacement")
    select_experience = r_json.get("cieeSelectExperience")
    remaining = (single_placement, double_placement, select_experience)
    response_dict = {
        "state_1": r_json.get("placementElectiveState1Id"),
        "state_2": r_json.get("placementElectiveState2Id"),
        "state_3": r_json.get("placementElectiveState3Id"),
        "state_4": r_json.get("placementElectiveFiveState1Id"),
        "state_5": r_json.get("placementElectiveFiveState2Id"),
        "state_6": r_json.get("placementElectiveFiveState3Id"),
        "state_7": r_json.get("placementElectiveFiveState4Id"),
        "state_8": r_json.get("placementElectiveFiveState5Id"),
    }
    states = []
    for k, v in response_dict.items():
        if v is not None:
            states.append(state_mappings.get(v))
    urban = r_json.get("urbanPlacementId")
    if urban == 5:
        urban = "Standard"
    elif urban == 6:
        urban = "Urban"
    elif urban == 17:
        urban = "Urban+"
    else:
        urban = "Urban"
    # [{"id":5,"type":"urban","name":"Standard Placement","sequence":1,"code":null},
    # {"id":6,"type":"urban","name":"Urban (city of at least 30,000)","sequence":2,"code":"hsjUrbanRequest"},
    # {"id":17,"type":"urban","name":"Urban+ (city of at least 75,000)","sequence":3,"code":"hsjUrbanPlusRequest"}]
    single_state = r_json.get("statePlacementId")
    california = r_json.get("californiaPlacementId")
    # [{"id":14,"type":"california","name":"Standard Placement","sequence":1,"code":null},
    # {"id":15,"type":"california","name":"California State","sequence":2,"code":"hsjCaliforniaStateRequest"},
    # {"id":16,"type":"california","name":"California within 50 miles of the Pacific coast","sequence":3,"code":"hsjCaliforniaCoastalRequest"}]
    florida = r_json.get("floridaPlacementId")
    # [{"id":18,"type":"florida","name":"Florida State","sequence":1,"code":"hsjFloridaStateRequest"},
    # {"id":19,"type":"florida","name":"No","sequence":2,"code":"hsjFloridaStateRequest"}]
    region = r_json.get("regionPlacementId")
    # [{"id":1,"displayName":"Region 1 – Northeast","systemName":"region1_ne","sequence":1},
    # {"id":9,"displayName":"Northeast","systemName":"region_ne_prex","sequence":1},
    # {"id":10,"displayName":"Mid-Atlantic","systemName":"region_ma_prex","sequence":2},
    # {"id":6,"displayName":"Region 2 – Mid-Atlantic","systemName":"region2_ma","sequence":2},
    # {"id":11,"displayName":"Southeast","systemName":"region_se_prex","sequence":3},
    # {"id":2,"displayName":"Region 3 – Southeast","systemName":"region3_se","sequence":3},
    # {"id":12,"displayName":"Central","systemName":"region_c_prex","sequence":4},
    # {"id":7,"displayName":"Region 4 – Warm South","systemName":"region4_ws","sequence":4},
    # {"id":13,"displayName":"Northwest","systemName":"region_nw_prex","sequence":5},
    # {"id":5,"displayName":"Region 5 – Great Lakes","systemName":"region5_gl","sequence":5},
    # {"id":4,"displayName":"Region 6 – Midwest","systemName":"region6_mw","sequence":6},
    # {"id":14,"displayName":"Southwest","systemName":"region_sw_prex","sequence":6},
    # {"id":8,"displayName":"Region 7 – Mountain West","systemName":"region7_mw","sequence":7},
    # {"id":3,"displayName":"Region 8 – Southwest","systemName":"region8_sw","sequence":8}]
    if region is not None and r_json.get('regionalOrStatePlacementPreferred') == "Regional":
        for state in state_mappings_orig:
            if region in state.get("regionId", []):
                states.append(state['name'])
    if california != 14 and california:
        states.append("California")
    if florida != 19 and florida:
        states.append("Florida")
    if single_state is not None and r_json.get('regionalOrStatePlacementPreferred') == "State":
        states.append(state_mappings.get(single_state))
    early_placement = r_json.get("placementElectiveEarlyDecisionMayRequested")
    return states, early_placement, urban, remaining, pre_p


def get_media(field_id):
    response = beacon_client.get(
        f"{BASE_URL}/beacon/participant/video/section/{field_id}",
        headers=BASE_HEADERS,
    )
    r_json = response.json()
    return r_json


def add_sports_and_interests(field_id):
    student_interests = {"selectables": [], "free_text": []}
    response = get_interests_hobbies(field_id)
    try:
        for interest_obj in response.json().get("participantSportInterestItems"):
            sportInterestedId = interest_obj.get("sportInterestId")
            student_interests["selectables"].append(
                sports_interests_mappings.get(sportInterestedId)
            )
    except:
        pass
    # print(student_interests)
    if (
        response.json().get("sportsOtherComment") is not None
        and response.json().get("sportsOtherComment") != ""
    ):
        student_interests["free_text"].append(response.json().get("sportsOtherComment"))

    if (
        response.json().get("personalQuestionInstrumentComment") is not None
        and response.json().get("personalQuestionInstrumentComment") != ""
    ):
        student_interests["instrument"] = response.json().get(
            "personalQuestionInstrumentComment"
        )

    if (
        response.json().get("personalQuestionExtraCurricularComment") is not None
        and response.json().get("personalQuestionExtraCurricularComment") != ""
    ):
        student_interests["free_text"].append(
            response.json().get("personalQuestionExtraCurricularComment")
        )

    if (
        response.json().get("personalQuestionCareerComment") is not None
        and response.json().get("personalQuestionCareerComment") != ""
    ):
        student_interests["free_text"].append(
            response.json().get("personalQuestionCareerComment")
        )

    if (
        response.json().get("personQuestionHighSchoolContributionComment") is not None
        and response.json().get("personQuestionHighSchoolContributionComment") != ""
    ):
        student_interests["free_text"].append(
            response.json().get("personQuestionHighSchoolContributionComment")
        )

    if (
        response.json().get("familyDescription") is not None
        and response.json().get("familyDescription") != ""
    ):
        student_interests["family_description"] = response.json().get(
            "familyDescription"
        )

    if (
        response.json().get("playTeamSportDescription") is not None
        and response.json().get("playTeamSportDescription") != ""
    ):
        student_interests["free_text"].append(
            response.json().get("playTeamSportDescription")
        )

    if (
        response.json().get("favoriteSubjects") is not None
        and response.json().get("favoriteSubjects") != ""
    ):
        student_interests["favorite_subject"] = response.json().get("favoriteSubjects")

    if (
        response.json().get("workOrVolunteerExperienceDescription") is not None
        and response.json().get("workOrVolunteerExperienceDescription") != ""
    ):
        student_interests["work"] = response.json().get(
            "workOrVolunteerExperienceDescription"
        )

    if (
        response.json().get("personalQuestionPreviousAbroadComment") is not None
        and response.json().get("personalQuestionPreviousAbroadComment") != ""
    ):
        student_interests["abroad"] = response.json().get(
            "personalQuestionPreviousAbroadComment"
        )

    if (
        response.json().get("personalQuestionForeignLanguagesComment") is not None
        and response.json().get("personalQuestionForeignLanguagesComment") != ""
    ):
        student_interests["languages"] = [
            response.json().get("personalQuestionForeignLanguagesComment")
        ]

    if (
        response.json().get("personalQuestionLanguagesSpokenAtHomeComment") is not None
        and response.json().get("personalQuestionLanguagesSpokenAtHomeComment") != ""
    ):
        if student_interests.get("languages") is not None:
            student_interests["languages"].append(
                response.json().get("personalQuestionLanguagesSpokenAtHomeComment")
            )
        else:
            student_interests["languages"] = [
                response.json().get("personalQuestionLanguagesSpokenAtHomeComment")
            ]

    # personalQuestionPreviousAbroadExperience
    # personalQuestionPreviousAbroadComment
    # personalQuestionPlayInstrument
    # personalQuestionInstrumentComment
    return student_interests


def fill_out_student(student):
    if student.get("usaHsId", "") == "TST25501":
        return
    student["namefirst"] = student["paxNameFirst"].title()
    student["genderdescription"] = "Male" if student.get("paxGender") == 1 else "Female"
    student["student_id"] = student["id"]

    response = get_basic_information(student["applicationId"])

    if response.status_code >= 400:
        logger.info(
            "Dropping student %s due to status code %s",
            student["applicationId"],
            response.status_code,
        )
    student.update(response.json())

    if student["statussystemname"] in [
        "inprogress",
        "canceled",
        "sentbacktoapplicant",
        "sentbacktointernationalrepresentative",
    ]:
        logger.info(
            "Dropping student %s due to status %s",
            student["applicationId"],
            student["statussystemname"],
        )
        return

    drop_keys = [
        "emailaddress",
        "birthcity",
        "birthcountryid",
        "birthcountry",
        "residenceCountryId",
        "namelast",
        "genderid",
        "productid",
        "skypeid",
        "namemiddle",
        "atlasId",  # usahsId
        "englishTest",
        # "englishTestScore",
        "hostFamily",
        "schoolReady",
    ]
    for key in drop_keys:
        student.pop(key)

    # mappings is necessary for fetching information in subsequent calls
    logger.debug(
        "Starting stage 2 hydration for application_id=%s", student["applicationid"]
    )

    comments = get_photo_details(student["applicationid"])
    student.update({"photo_comments": comments})

    response = get_category_mappings(student["applicationid"])
    mappings = {x.get("sectionName"): x.get("id") for x in response.json()}
    student.update({"mappings": mappings})

    # add interests and hobbies

    interest_hobbies_field = student["mappings"].get("interestAndHobbies")
    student_interests = add_sports_and_interests(interest_hobbies_field)
    student.update({"interests": student_interests})

    # get program type

    program_type = get_program_type(student["applicationid"])
    student.update({"program_type": program_type})

    # get states, I believe this needs additional work as of now

    student_placement_field = student["mappings"].get("hsjPlacementOptions")
    hsjPlacementOptions, early_placement, urban, remaining, pre_p = (
        get_placement_requests(student_placement_field)
    )
    if pre_p is not None and pre_p is False:
        logger.debug("Student marked preplacement and uninterested in normal placement")
        student.update({"statussystemname": "preplacement"})
    elif pre_p is not None and pre_p is True:
        logger.debug(
            "Student marked preplacement and possibly interested in normal placement"
        )
        student.update({"statussystemname": "preplacement"})
    student.update({"states": hsjPlacementOptions})
    student.update({"early_placement": early_placement})
    student.update({"urban": urban})
    single_placement = remaining[0]
    double_placement = remaining[1]
    select_experience = remaining[2]
    student.update({"single_placement": single_placement})
    student.update({"double_placement": double_placement})
    student.update({"select_experience": select_experience})

    # get health , religion, etc

    health_field = student["mappings"].get("hsjHealthInformation")
    # input(health_field)
    allergies = get_personal_information(health_field)
    student.update({"can_live_w_pets": allergies.json()["environmentLiveWithPets"]})
    student.update({"religion": allergies.json()["religion"]})
    student.update(
        {"pet_comment": allergies.json().get("environmentLiveWithPetsComment")}
    )
    student.update({"gender_explanation": allergies.json().get("genderExplanation")})
    student.update({"diet_comment": allergies.json().get("dietComment")})
    student.update(
        {"allergies_comment": allergies.json().get("environmentAllergiesComment")}
    )
    student.update({"dietSpecial": allergies.json().get("dietSpecial")})
    student.update(
        {"environmentAllergies": allergies.json().get("environmentAllergies")}
    )
    student.update(
        {
            "religiousFrequency": allergies.json().get(
                "religiousServiceAttendanceFrequencyId"
            )
        }
    )

    # get both student and family messages

    messages_field = student["mappings"].get("hostFamilyMessages")
    messages_resp = get_host_family_messages(messages_field)
    student.update(
        {
            "messages": [
                messages_resp.json()["introduction"],
                messages_resp.json()["hostFamilyLetter"],
                messages_resp.json()["parentLetter"],
            ]
        }
    )

    # get adjusted age

    year = student.get("program_type")
    year_pattern = r"\d{4}"
    if "jan" in year.lower():
        start_date = "01/01"
    else:
        start_date = "08/01"
    program_year_number = re.findall(year_pattern, year)[0]
    bd = datetime.strptime(student.get("dateofbirth"), "%m/%d/%Y")
    aug_1 = datetime.strptime(f"{start_date}/{program_year_number}", "%m/%d/%Y")
    relative_age = math.floor((aug_1 - bd).days / 365)
    student.update({"adjusted_age": relative_age})

    # get media if available

    media_field = student["mappings"].get("photos")
    media = get_media(media_field)
    if media.get("hasVideo") is True:
        student.update({"media": True})
        student.update({"media_link": media.get("videoLink")})
    else:
        student.update({"media": False})

    # get health info

    health_field = student["mappings"].get("hsjHealthInformation")
    health = get_health_information(health_field)
    student.update(
        {
            "health_comments": [
                health.json().get("anyPhysicalDisabilityComment"),
                health.json().get("preexistingMedicalConditionsComment"),
                health.json().get("anyMedicalInfoImportantForCIEEComment"),
            ]
        }
    )
    test_score, _, test_type = student["englishTestScore"].partition(" ")
    if "2.0" in test_type:
        student.update({"englishTestScore": f"{(int(test_score) / 800) * 100:0.01f} %"})
    elif "1" in test_type:
        student.update({"englishTestScore": f"{(int(test_score) / 300) * 100:0.01f} %"})

    if student.get("usaHsId") is None:
        student["usaHsId"] = ""
    if student.get("usahsId") is None:
        student["usahsId"] = ""

    insert_full_student(student)


def run_stage_2_multi_threaded(students):
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        pool.map(
            fill_out_student,
            ((student) for student in students),
        )
