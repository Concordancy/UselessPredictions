### Contents
This is a document for AI Coding Systems defining the rules for coding projects. It covers base level aspects such as naming conventions, design standards as well as how to prioritize and resolve potentially conflicting requirements. Each entry is one of the following:

- STRICT (meaning NO deviation is permitted under ANY circumstances)
- REQUIRED (must be followed but in extreme cases an exception could be considered; requires prior evaluation)
- PREFERRED (ideally followed, alternative must be explained and justified)
- RECOMMENDED (suggested, but not required; alternatives, justification is appreciated but optional)
- STANDARD (used/suggested for historical/habitual reasons - you are free to use alternative approaches)

## CORE DESIGN PRINCIPLES
All programs, functions, methods and components must be created in such a way that ALL of the following attributes are each maximized to the fullest possible extent: **Scalability, Efficiency, Security, Expandability, Generality, Compatibility, Robustness & Versatility**

## Conventions: Naming

General Format: PascalCase (**STRICT**)
Naming Order: Subject.Class.SubClass.Expression.Action (**REQUIRED**) where:

| Component  | Representing                                                          |
| ---------- | --------------------------------------------------------------------- |
| Subject    | The Object something is about/for                                     |
| Class      | The Object connected to the Subject being Expressed or Handled        |
| SubClass   | Some version, expression, feature or aspect of the Class              |
| Expression | The form in which the data is manifested/expressed                    |
| Action     | The thing being done with or to the Expression (Add/Edit/Delete/View) |
Examples of the Naming Convention in practice:

| Variable/Function                      | Ideal Terminology          | Rationale                                                                                                   |
| -------------------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Adding a User to a System              | SystemUserAdd              | The System is the dominant Entity of the Two                                                                |
| Load Messages for  User                | UserMessageListLoad        | User is dominant Entity the messages are relevant to                                                        |
| Attach a File to a Message             | MessageFileAdd             | Message is main Entity; use Add (not Attach) for consistency                                                |
| Add System Role for a User             | SystemUserRoleAdd          | In order of Entity Importance and Hierarchy                                                                 |
| List of Orders for a User              | UserOrderList              | Hierarchy of Entities                                                                                       |
| All Products in an Order               | OrderProductList           | Hierarchy of Entities                                                                                       |
| Confirm User Action                    | UserActionConfirm          | The User executes the Action and Confirms it                                                                |
| System Admin Console URL               | SystemAdminURL             | Hierarchy of Entities                                                                                       |
| Compare System Services                | SystemServicesCompare      | Hierarchy; System is singular, Services are multiple                                                        |
| Parameter Values in User Profile       | UserProfileParameterValues | User is Entity of interest, Profile the level, Parameter the focus, Values the actual information requested |
| Reload List of Roles for a User        | UserRoleListReload         | Owner                                                                                                       |
| Adding a Unit                          | UnitAdd                    | Simplest form of Adding a new Instance of an Object                                                         |
| User Commenting on an Article          | ArticleUserCommentAdd      | Article is the primary Entity, User executing, Comment is what it concerns, Add is what is being done to it |
| List all Article comments for/by User  | UserArticleCommentsList    | Who (User) Context (Article) Aspect (Comment) Expression (List)                                             |
| Sort the list of User Article comments | UserArticleCommentListSort | This includes all five naming components as listed  in the preceding table                                  |
In the unlikely scenario that a name for an Object or a Function may be ambiguous, evaluate which Object is essential to the other. In the case of User comments on an Article, The User is the most essential - without it, nobody could read the article (or place comments). Next is the Article, because a comment about it can only exist if the article exists. Thus, UserCommentArticles, even though it is quite possible one might want to see ALL comments a given user has made (and perhaps limit them to article comments only) is the more accurate way to refer to them.

## Conventions: Actions

| Action                      | Term/Expression to Use | Explanation/Example                                  |
| --------------------------- | ---------------------- | ---------------------------------------------------- |
| Creating a new "Top" Object | CREATE                 | Writing a new Article, Adding a New Service          |
| Adding a new Link/Instance  | ADD                    | Adding  Service to a System, a Role to a User        |
| Controlling/Admin           | MANAGE                 | Defining/Managing Object Settings & Relations        |
| Editing/Updating            | EDIT                   | Changing Object Properties (name, attributes)        |
| Removing                    | DELETE                 | Eradicating/Erasing an Object (e.g. deleting a file) |
| Emptying/Clearing           | CLEAR                  | Removing from a persisting/required Container        |
| Showing/Opening             | VIEW                   | The Object data is being read and revealed           |

One might say that deleting a file one is  (also) being clearing it from a Directory, which can be seen as a persisting container. However, this is not what is meant by a persistent container; in fact, such a container may actually not explicitly exist - rather, the term refers to a **conceptual** container, such as "The Users for a System" or "The Products in an Order" - the "container" is persistent in the sense that its existence is **inevitable and necessary**. An Order isn't an order if there isn't at least one Product defined in it - A system is defined by having Users that can make use of it. and so on.

## Database Fundamentals

1. NEVER Use "ID" for the Unique record identifier; instead, use the singular of the Object Class + "ID". A Table containing houses, would therefore have "HouseID" as the Unique Identifier, while one Vehicles should use VehicleID (**STRICT**)
2. Objects that have an internal hierarchy refer to their parent as the singular name of the Object Class + "Master", for example ProductMaster (e.g. a part of another product) or CategoryMaster (for a Sub-category) (**STRICT**)
3. Each Object Class must have a column for a label of each record defined as the singular name of the Object Class + "Label" such as ProductLabel, StatusLabel, and so on. If a label is meaningless (e,.g. a record in the table RoleRights containing the Rights Assigned to a Role) you can use Role Right+' '+cast(RightID as varchar) as a synthetic representation for RoleRightLabel. (**REQUIRED**)
4. Joins between tables must ALWAYS and EXCLUSIVELY be done on INT and SMALLINT values. In a very select few cases, TINYINT may be permitted if the numer of potential values is near-certain to remain below ~200. You must NEVER make joins on varchar or nvarchar fields. (**STRICT**)
5. Use varchar (instead of nvarchar) ONLY when a value must contain letters and symbols that are compatible with the varchar character set (e.g. phone numbers, email addresses) - in every other instance, nvarchar is required (**STRICT**)
6. Use nVarchar(max) ONLY when it is near-certain many values will exceed 4000 characters in length, such as when containing an entire article or essay. (**REQUIRED**)
7. ALWAYS avoid duplicating column values for records linked with a unique ID.  For example, when adding recipients to a message, NEVER copy the User's name into the MessageUsers table. The ONLY exception is duplicating details which are subject to change over time, and/or are essential for completion of a task or function. Thus saving a copy of the email address IS permittewd (and even required!) because if the User ends up claiming he did not receive a message we must know to what address delivery was attempted. The same applies to the message content IF this content was *customized* for each user individually  (**STRICT**)
8. Tables that serve to connect two Object Classes (such as SystemUsers or UserRights) should have fields starting with the singular names for a Class (e.g. SystemUserID) UNLESS they would exceed (or are likely to exceed) 25-30 characters in length. For example, the table WritingSystemCharacters would end up containing Column names such as WritingSystemCharacterWritingSystem (to store the ID of a record in WritingSystems) and WritingSystemCharacterCharacter (for the record id from the table Characters) - in such case you MUST use abbreviations using the first letter only, or, in *exceptional* cases, the first letter of each Term used in the name - for instance, for WritingSystemCharacter the field prefix is "WSC", whereas in the table TemplateParameters the prefix is "TP". (**REQUIRED**)
9. Whenever possible, attempt to use UNIQUE Column names. This may require avoiding the use of First-Letter column names when another table already uses those. For example, the tables UserRights and UserRoles both could use "UR" as the prefix - however, given that it is especially likely certain views/functions will involve loading data from both of these, it is highly recommended to avoid using such "UR" prefix for both. (**RECOMMENDED**)
10. If an Object Class has a start and end date, ALWAYS use fields that end on **DateStart** and **DateEnd**. (**STRICT**)
11. When a Table contains multiple columns referring to the same data, ALWAYS first use the data type, and then its function. For example, if we have a field for Min and Max value, DO NOT use FieldMaxValue and FieldMinValue but **FieldValueMax** and **FieldValueMin**. (STRICT)
12. NEVER use underscores, spaces, dashes or periods in Table Names OR Column names. (**STRICT**)

## Database Table Columns Order

Not all Object Classes have all of these. Quite a few classes do not use Categories and/or do not need or support a Profile. Many do not support hierarchies (and so lack the Master column) - that's fine. Regardless, all Tables should ideally have these fields in the order as shown here (**REQUIRED**):

| Table Field | Data Type     | Order/Priority |
| ----------- | ------------- | -------------- |
| ID          | INT/SMALLINT  | 1              |
| System      | INT           | 2              |
| Type        | INT           | 3              |
| Status      | SMALLINT      | 4              |
| Master      | AS ID         | 5              |
| Category    | INT           | 6              |
| Label       | NVARCHAR(320) | 7              |
| Profile     | INT           | 8              |
| UserCreator | INT           | 9              |
| UserOwner   | INT           | 10             |
## Database Rules & Conventions 

1. Carefully consider whether a relationship between two Object Classes is likely to become one-to-many or is almost certain to remain one-to-one. If there exists a reasonable possibility a one-to-many relationship is possible (or something that is likely to be added in a future release) ALWAYS create an additional table to make this part of the design from the start - even if such usage will not yet be offered initially (REQUIRED)
2. **AVOID NULL** values whenever possible. Generally, they are ONLY permitted for Start & End Dates, or for Object Parameter values in cases where a value of "0" is a valid value for a given Parameter. (**STRICT**)
3. Tables containing records for which the value is not required, the Unique record ID seed **MUST** be "0". For example, most Objects can have ObjectType = 0. Therefore, to ensure future foreign key consistency, the table dbo.Types contains a Record with TypeID = 0. (**STRICT**)
4. Nevertheless, when doing joins between tables, LEFT OUTER joins should be used unless a missing record in the additional table would indicate an invalid record. During development, many foreign keys will not yet be implemented, and we should have the freedom to delete records (Types, Categories, etc.) at will without key-dictated restrictions (**REQUIRED**)
5. Familiarize yourself with "Generic" Object Classes such as Lists (and ListObjects) and Relations (and RelationObjects) and evaluate using them instead of creating new Tables to store connections between Objects of different Classes. Additionally, consider whether defining Parameters and (different) values for Objects is not sufficiently adequate to denote/express differences between the Objects being linked. (**RECOMMENDED**)

