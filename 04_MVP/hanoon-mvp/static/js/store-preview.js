const approvedDescription = sessionStorage.getItem("hanoonApprovedDescription");
if (approvedDescription) {
    document.getElementById("approved-description").textContent = approvedDescription;
}
