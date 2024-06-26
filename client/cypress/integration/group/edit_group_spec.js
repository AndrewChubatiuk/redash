describe("Edit Group", () => {
  beforeEach(() => {
    cy.login();
    cy.visit("/groups/1");
  });

  it("renders the page and takes a screenshot", () => {
    cy.getByTestId("Group").within(() => {
      cy.get("h3").should("contain", "admin");
      cy.get("td").should("contain", Cypress.env("CYPRESS_LOGIN_NAME"));
    });

    cy.percySnapshot("Group");
  });
});
