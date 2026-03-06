from models.student import FullStudent


def _full_student_dict(student: dict) -> FullStudent:
    # helper func to avoid having to retype this entire section each time
    return FullStudent(
        first_name=student["namefirst"],
        app_id=student["applicationid"],
        pax_id=student["participantid"],
        country=student["residenceCountry"],
        gpa=student["schoolInfoGPA"],
        english_score=student["englishTestScore"],
        applying_to_grade=student["gradeApplyingTo"],
        usahsid=student["usahsId"],
        program_type=student["program_type"]
        .replace("High School USA ", "")
        .replace("Exchange", "")
        .replace("2026 ", "")
        .strip(),
        adjusted_age=student["adjusted_age"],
        gender_desc=student["genderdescription"],
        id=student["student_id"],
        current_grade=student["currentGradeLevel"],
        status=student["statussystemname"],
        states=student["states"],
        early_placement=student["early_placement"],
        urban_request=student["urban"],
        single_placement=student["single_placement"],
        double_placement=student["double_placement"],
        free_text_interests=student["interests"]["free_text"],
        family_description=student["interests"]["family_description"],
        favorite_subjects=student["interests"]["favorite_subject"],
        selected_interests=student["interests"]["selectables"],
        photo_comments=student["photo_comments"],
        religion=student["religion"],
        allergy_comments=student["allergies_comment"],
        dietary_restrictions=student["diet_comment"],
        religious_frequency=student["religiousFrequency"],
        intro_message=student["messages"][0],
        message_to_host_family=student["messages"][1],
        message_from_natural_family=student["messages"][2],
        media_link=student.get("media_link", ""),
        health_comments=student["health_comments"],
        live_with_pets=student["can_live_w_pets"],
        placement_status=student["placementStatusName"].title(),
        tuition_placement=student["tuition_placement"]
    )
